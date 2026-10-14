"""
Sage adapter — hospital finance KPIs for the dashboards, Credit Control and services.

Since Roy Books (2026-10) these delegate to src.fin.credit: HMO / corporate debt from
Hope billing less Sage receipts (and the books once live), P&L and cash from the
ledger. The royan_billing queries below remain only as the fallback if that fails.

The original Sage/Placeware CSV import pipeline has been removed from RoyanHealth.
Finance metrics are now computed directly from the royan_billing and royan_payments
tables that were populated by the DRM Hope ETL.

Batch helpers, GL snapshot, and inventory functions remain as no-op stubs since
those data sources do not exist in the hospital deployment.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...db import db
from ...cache import ttl_cache

logger = logging.getLogger("sage_adapter")


# ---------------------------------------------------------------------------
# Batch helpers — always return None (no Sage batch exists in hospital DB)
# ---------------------------------------------------------------------------

def get_sage_kpi_batch_id() -> Optional[str]:
    return None


def _latest_batch_for_table(table: str, client: Any = None) -> Optional[str]:
    return None


# ---------------------------------------------------------------------------
# Finance KPIs — sourced from royan_billing
# ---------------------------------------------------------------------------

@ttl_cache(ttl_seconds=300, ignore_kwargs=("client",), tags=("finance", "billing", "executive"))
def kpis(client: Any = None) -> Dict[str, Any]:
    """Finance KPIs from Roy Books (src.fin.credit); the royan_billing version below is the fallback.

    Scoped to bills RAISED IN THIS SYSTEM (external_source IS NULL).

    The Hope migration brought across 259,067 bills spanning 2016-2026 and
    249,232 payments — but the payments arrived carrying only patient_id, never
    a billing_id, so not one of them could be matched back to the bill it
    settled. Every migrated bill therefore landed on status='pending' with its
    full balance outstanding, and since all of them are older than 30 days,
    every one also satisfies the overdue test. That is what produced a
    Naira1.73bn "overdue" figure on a hospital that has billed Naira7,000
    through this system.

    Those rows are ten years of closed Hope history, not money Royan is owed.
    Live AR is counted here; the legacy total is returned separately under
    "legacy" so it stays visible and auditable rather than silently dropped.
    Royan's real receivables ledger lives in Sage.
    """
    try:
        from src.fin import credit
        return credit.kpis()
    except Exception:
        logger.exception("Roy Books KPIs failed; falling back to royan_billing")
    conn = db.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(subtotal), 0)                                              AS total_revenue,
                COALESCE(SUM(patient_balance)
                    FILTER (WHERE status IN ('pending','partial','disputed')), 0)       AS ar_total,
                COUNT(*)
                    FILTER (WHERE status IN ('pending','partial','disputed'))           AS ar_count,
                COALESCE(SUM(patient_balance)
                    FILTER (WHERE status IN ('pending','partial')
                            AND billed_at < NOW() - INTERVAL '30 days'), 0)             AS ar_overdue,
                COUNT(*)
                    FILTER (WHERE status IN ('pending','partial')
                            AND billed_at < NOW() - INTERVAL '30 days')                 AS ar_overdue_count
            FROM public.royan_billing
            WHERE external_source IS NULL
        """)
        row = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(patient_balance), 0)
            FROM public.royan_billing
            WHERE external_source IS NOT NULL
              AND status IN ('pending','partial','disputed')
        """)
        legacy = cur.fetchone()

        return {
            "total_revenue":    float(row[0]),
            "ar_total":         float(row[1]),
            "ar_overdue":       float(row[3]),
            # Nested form, which is what intelligence.py and analytics.py both
            # reach for. It was never returned before, so both fell through to
            # a fallback that read the Naira amount as an invoice count.
            "ar": {
                "total_balance":  float(row[1]),
                "total_amount":   float(row[1]),
                "count":          int(row[2]),
                "overdue_amount": float(row[3]),
                "overdue_count":  int(row[4]),
            },
            "legacy": {
                "unreconciled_count":  int(legacy[0]),
                "unreconciled_amount": float(legacy[1]),
                "note": ("Migrated Hope bills whose payments could not be matched "
                         "(Hope payments carry no bill reference). Historical, "
                         "excluded from live AR."),
            },
            "total_cogs":       0.0,
            "gross_margin_pct": 0.0,
            "ap_total":         0.0,
            "inventory_value":  0.0,
            "cash_position":    0.0,
        }
    except Exception:
        logger.exception("kpis query failed")
        return {
            "total_revenue": 0.0, "ar_total": 0.0, "ar_overdue": 0.0,
            "ar": {"total_balance": 0.0, "total_amount": 0.0, "count": 0,
                   "overdue_amount": 0.0, "overdue_count": 0},
            "total_cogs": 0.0, "gross_margin_pct": 0.0, "ap_total": 0.0,
            "inventory_value": 0.0, "cash_position": 0.0, "_no_data": True,
        }
    finally:
        db.pool.putconn(conn)


@ttl_cache(ttl_seconds=300, ignore_kwargs=("client",), tags=("finance", "billing"))
def ar_trend_summary(client: Any = None, periods: int = 6) -> Dict[str, Any]:
    """Monthly billed and HMO/corporate debt at month end (Roy Books); royan_billing as fallback."""
    try:
        from src.fin import credit
        return credit.trend(periods)
    except Exception:
        logger.exception("Roy Books trend failed; falling back to royan_billing")
    conn = db.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', billed_at), 'YYYY-MM') AS period,
                COALESCE(SUM(subtotal), 0)                          AS billed,
                COALESCE(SUM(patient_balance), 0)                   AS outstanding
            FROM public.royan_billing
            WHERE billed_at >= NOW() - (%s * INTERVAL '1 month')
            GROUP BY DATE_TRUNC('month', billed_at)
            ORDER BY 1
        """, (periods,))
        rows = cur.fetchall()
        return {
            "periods": [
                {"period": r[0], "billed": float(r[1]), "outstanding": float(r[2])}
                for r in rows
            ]
        }
    except Exception:
        logger.exception("ar_trend_summary query failed")
        return {"periods": [], "_no_data": True}
    finally:
        db.pool.putconn(conn)


@ttl_cache(ttl_seconds=300, ignore_kwargs=("client",), tags=("finance", "billing"))
def ar_aging_buckets(client: Any = None) -> Dict[str, Any]:
    """What debtors owe, aged (Roy Books: HMO / corporate billing less receipts); royan_billing as fallback."""
    try:
        from src.fin import credit
        return credit.aging_buckets()
    except Exception:
        logger.exception("Roy Books ageing failed; falling back to royan_billing")
    conn = db.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(patient_balance) FILTER (WHERE age_days <= 30), 0),
                COALESCE(SUM(patient_balance) FILTER (WHERE age_days BETWEEN 31 AND 60), 0),
                COALESCE(SUM(patient_balance) FILTER (WHERE age_days BETWEEN 61 AND 90), 0),
                COALESCE(SUM(patient_balance) FILTER (WHERE age_days > 90), 0)
            FROM (
                SELECT patient_balance,
                       EXTRACT(DAY FROM NOW() - billed_at)::int AS age_days
                FROM public.royan_billing
                WHERE status IN ('pending', 'partial', 'disputed')
            ) aged
        """)
        row = cur.fetchone()
        return {
            "0_30":    float(row[0]),
            "1_30":    float(row[0]),
            "current": float(row[0]),
            "31_60":   float(row[1]),
            "61_90":   float(row[2]),
            "91_plus": float(row[3]),
            "over_90": float(row[3]),
        }
    except Exception:
        logger.exception("ar_aging_buckets query failed")
        return {
            "0_30": 0.0, "31_60": 0.0, "61_90": 0.0, "91_plus": 0.0,
            "current": 0.0, "1_30": 0.0, "over_90": 0.0, "_no_data": True,
        }
    finally:
        db.pool.putconn(conn)


# ---------------------------------------------------------------------------
# Stubs — data sources not applicable to hospital deployment
# ---------------------------------------------------------------------------

def ar_aging_customers(
    client: Any = None,
    limit: int = 50,
    min_overdue: float = 0.0,
    bucket: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Debtors in one ageing bucket (or all), largest first."""
    try:
        from src.fin import credit
        rows = [r for r in credit.aging_customers(bucket) if r["total_balance"] >= min_overdue]
        return rows if bucket else rows[:limit]
    except Exception:
        logger.exception("Roy Books debtor list failed")
        return []


def get_latest_gl_snapshot(client: Any = None, limit: int = 1000) -> List[Dict[str, Any]]:
    return []


def latest_inventory_snapshot(client: Any = None) -> List[Dict[str, Any]]:
    return []


def inventory_by_skus(skus: List[str], client: Any = None) -> List[Dict[str, Any]]:
    return []
