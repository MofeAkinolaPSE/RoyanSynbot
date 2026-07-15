"""
Automated Workflow Scheduler
Implements scheduled triggers for workflow automation loops.
Runs periodic checks and triggers appropriate workflows.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.db import db
from src.constants import TABLE_KPI_PROMOTIONS
from src.workflow.batch_locking import lock_batch, is_batch_locked
from src.workflow.credit_risk import apply_credit_action, is_customer_flagged

logger = logging.getLogger(__name__)

# Configuration for automation thresholds
AUTOMATION_CONFIG = {
    "low_stock_threshold": 10,  # Trigger replenishment below this qty
    "expiry_warning_days": 30,  # Create promotion if expiring within X days
    "auto_promotion_discount": 15.0,  # Default discount % for expiry promotions
    "ar_aging_critical_days": 90,  # Flag customer if AR > X days
    "ar_aging_warning_days": 60,  # Warn if AR > X days
    "scheduler_interval_minutes": 5,  # How often to run checks
}


class WorkflowAutomation:
    """
    Automated workflow triggers that detect conditions and initiate actions.
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the automation scheduler."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Workflow automation scheduler started")

    async def stop(self):
        """Stop the automation scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Workflow automation scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop."""
        interval = AUTOMATION_CONFIG["scheduler_interval_minutes"] * 60
        while self._running:
            try:
                await asyncio.to_thread(self._run_all_checks)
            except Exception as e:
                logger.exception(f"Automation check failed: {e}")
            await asyncio.sleep(interval)

    def _run_all_checks(self):
        """Run all automation checks (synchronous — offloaded to a thread by the caller)."""
        logger.debug("Running workflow automation checks...")

        # 1. Check for low stock and trigger replenishment
        self._check_low_stock()

        # 2. Check for near-expiry items and create promotions
        self._check_expiry_prevention()

        # 3. Check for AR aging and flag credit risks
        self._check_credit_risk()

        logger.debug("Workflow automation checks completed")

    def _check_low_stock(self):
        """
        Check for low stock items and trigger replenishment.
        Creates replenishment orders for items below threshold.

        Batched: 1 query to list candidates + 1 query to check existing
        replenishment requests + 1 bulk insert, regardless of how many
        prescriptions are pending — instead of 2 queries per item.
        """
        try:
            threshold = AUTOMATION_CONFIG["low_stock_threshold"]

            # Query pharmacy prescriptions pending dispensing
            result = db.table("royan_prescriptions").select(
                "id, drug_name, drug_code, quantity, unit"
            ).eq("status", "pending").execute()

            items = result.data if hasattr(result, 'data') else []
            if not items:
                return

            # Dedupe by SKU — only one replenishment request per SKU per cycle
            # (first occurrence wins, matching the old per-row behavior where
            # the first insert for a SKU made every later row see it as "already pending").
            candidates: Dict[str, Dict[str, Any]] = {}
            for item in items:
                sku = item.get("drug_code") or item.get("drug_name")
                if sku and sku not in candidates:
                    candidates[sku] = item

            if not candidates:
                return

            # One query for every SKU that already has a pending replenishment request
            existing = db.table("replenishment_requests").select("sku").eq(
                "status", "recommended"
            ).in_("sku", list(candidates.keys())).execute()
            existing_skus = {row.get("sku") for row in (existing.data or [])}

            new_requests = []
            for sku, item in candidates.items():
                if sku in existing_skus:
                    continue
                current = 0  # prescription is pending — treat as 0 stock consumed
                safety = item.get("quantity", threshold * 2)
                reorder_qty = max(safety - current, threshold * 2)
                new_requests.append({
                    "sku": sku,
                    "requested_qty": reorder_qty,
                    "status": "recommended",
                    "created_by": "auto_low_stock",
                    "notes": f"Auto-generated: stock {current} below threshold {threshold}",
                })

            if new_requests:
                db.table("replenishment_requests").insert(new_requests).execute()
                for req in new_requests:
                    logger.info(f"Auto-replenishment created: {req['sku']} qty={req['requested_qty']}")

        except Exception as e:
            logger.error(f"Low stock check failed: {e}")

    def _check_expiry_prevention(self):
        """
        Check for near-expiry items and create discount promotions.
        Locks batches that are expired.

        Batched: the promotion-existence check and the promotion/KPI inserts
        happen once for the whole cycle instead of once per near-expiry item.
        (Batch locking stays a plain loop — batch_locking.py is currently a
        no-op stub with no DB cost.)
        """
        try:
            warning_days = AUTOMATION_CONFIG["expiry_warning_days"]
            discount = AUTOMATION_CONFIG["auto_promotion_discount"]
            cutoff = (datetime.utcnow() + timedelta(days=warning_days)).isoformat()

            # Query dispensing records for near-expiry drugs
            result = db.table("royan_dispensing").select(
                "drug_name, batch_number, quantity_dispensed, expiry_date"
            ).lt("expiry_date", cutoff).gt("quantity_dispensed", 0).execute()

            items = result.data if hasattr(result, 'data') else []
            if not items:
                return

            now = datetime.utcnow()
            expired_batch_ids: List[str] = []
            near_expiry: Dict[tuple, Dict[str, Any]] = {}  # (sku, batch_id) -> item

            for item in items:
                sku = item.get("drug_name")
                batch_id = item.get("batch_number")
                expiry = item.get("expiry_date")

                if not expiry:
                    continue
                try:
                    exp_date = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                except Exception:
                    continue

                if exp_date < now.replace(tzinfo=exp_date.tzinfo):
                    if batch_id:
                        expired_batch_ids.append(batch_id)
                    continue

                key = (sku, batch_id)
                if key not in near_expiry:
                    near_expiry[key] = item

            for batch_id in expired_batch_ids:
                if not is_batch_locked(batch_id):
                    lock_batch(batch_id, "Auto-locked: Expired", "system")
                    logger.warning(f"Batch {batch_id} auto-locked due to expiry")

            if not near_expiry:
                return

            # One query for every SKU that might already have a promotion,
            # then refine to exact (sku, batch_id) matches in Python.
            skus = list({sku for sku, _ in near_expiry.keys()})
            existing = db.table("promotions").select("sku, batch_id").in_("sku", skus).execute()
            existing_keys = {(row.get("sku"), row.get("batch_id")) for row in (existing.data or [])}

            new_promotions = []
            new_kpi_rows = []
            for (sku, batch_id), item in near_expiry.items():
                if (sku, batch_id) in existing_keys:
                    continue
                qty = item.get("quantity_dispensed", 0)
                new_promotions.append({
                    "sku": sku, "batch_id": batch_id, "qty": qty,
                    "discount_pct": float(discount), "created_by": "system_auto_expiry",
                })
                new_kpi_rows.append({
                    "sku": sku, "batch_id": batch_id, "qty": qty,
                    "discount_pct": discount, "created_by": "system_auto_expiry",
                })

            if new_promotions:
                db.table("promotions").insert(new_promotions).execute()
                db.table(TABLE_KPI_PROMOTIONS).insert(new_kpi_rows).execute()
                for p in new_promotions:
                    logger.info(f"Auto-promotion created: {p['sku']} batch={p['batch_id']} discount={discount}%")

        except Exception as e:
            logger.error(f"Expiry prevention check failed: {e}")

    def _check_credit_risk(self):
        """
        Check AR aging and flag credit risk customers.
        Automatically adjusts credit limits for risky customers.
        """
        try:
            critical_days = AUTOMATION_CONFIG["ar_aging_critical_days"]
            warning_days = AUTOMATION_CONFIG["ar_aging_warning_days"]
            
            # Query hospital billing for outstanding patient balances
            result = db.table("royan_billing").select(
                "patient_id, bill_number, patient_balance, billed_at, external_source"
            ).gt("patient_balance", 0).execute()

            rows = result.data if hasattr(result, 'data') else []

            # Group by patient — skip historical Hope imports (only check native system bills)
            customer_ar: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                if row.get("external_source") == "hope":
                    continue
                cid = str(row.get("patient_id", ""))
                if not cid:
                    continue
                if cid not in customer_ar:
                    customer_ar[cid] = {
                        "name": f"Patient #{cid}",
                        "total_ar": 0,
                        "oldest_invoice": None,
                        "overdue_days": 0,
                    }
                
                amount = float(row.get("patient_balance", 0))
                customer_ar[cid]["total_ar"] += amount
                
                inv_date = row.get("billed_at")
                if inv_date:
                    try:
                        inv_dt = datetime.fromisoformat(str(inv_date).replace("Z", "+00:00"))
                        days_old = (datetime.utcnow().replace(tzinfo=inv_dt.tzinfo) - inv_dt).days
                        if days_old > customer_ar[cid]["overdue_days"]:
                            customer_ar[cid]["overdue_days"] = days_old
                            customer_ar[cid]["oldest_invoice"] = inv_date
                    except:
                        pass
            
            # Check each customer
            for cid, data in customer_ar.items():
                days = data["overdue_days"]
                
                if days >= critical_days:
                    # Critical - flag customer
                    if not is_customer_flagged(cid):
                        apply_credit_action(cid, "flagged", {
                            "reason": f"AR overdue {days} days",
                            "ar_amount": data["total_ar"],
                            "oldest_invoice": data["oldest_invoice"],
                            "trigger": "auto_ar_critical",
                        })
                        logger.warning(f"Customer {cid} flagged: AR overdue {days} days")
                        
                elif days >= warning_days:
                    # Warning - reduce credit limit
                    apply_credit_action(cid, "limit_reduce", {
                        "reason": f"AR overdue {days} days (warning)",
                        "ar_amount": data["total_ar"],
                        "trigger": "auto_ar_warning",
                    })
                    logger.info(f"Customer {cid} credit reduced: AR overdue {days} days")
                    
        except Exception as e:
            logger.error(f"Credit risk check failed: {e}")


# Singleton instance
_automation: Optional[WorkflowAutomation] = None


def get_workflow_automation() -> WorkflowAutomation:
    """Get or create the workflow automation singleton."""
    global _automation
    if _automation is None:
        _automation = WorkflowAutomation()
    return _automation


async def start_workflow_automation():
    """Start the workflow automation scheduler."""
    automation = get_workflow_automation()
    await automation.start()


async def stop_workflow_automation():
    """Stop the workflow automation scheduler."""
    automation = get_workflow_automation()
    await automation.stop()


# Manual trigger for testing
async def run_automation_checks_once():
    """Run all automation checks once (for testing/manual trigger)."""
    automation = get_workflow_automation()
    await asyncio.to_thread(automation._run_all_checks)
