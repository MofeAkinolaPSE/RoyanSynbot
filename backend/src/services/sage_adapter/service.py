"""
Sage adapter — hospital finance KPIs sourced from royan_billing.

The original Sage/Placeware CSV import pipeline has been removed from SynbotHealth.
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
    """Revenue and AR KPIs derived from royan_billing."""
    conn = db.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(SUM(subtotal), 0)                                              AS total_revenue,
                COALESCE(SUM(patient_balance)
                    FILTER (WHERE status IN ('pending','partial','disputed')), 0)       AS ar_total,
                COALESCE(SUM(patient_balance)
                    FILTER (WHERE status IN ('pending','partial')
                            AND billed_at < NOW() - INTERVAL '30 days'), 0)             AS ar_overdue
            FROM public.royan_billing
        """)
        row = cur.fetchone()
        return {
            "total_revenue":    float(row[0]),
            "ar_total":         float(row[1]),
            "ar_overdue":       float(row[2]),
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
            "total_cogs": 0.0, "gross_margin_pct": 0.0, "ap_total": 0.0,
            "inventory_value": 0.0, "cash_position": 0.0, "_no_data": True,
        }
    finally:
        db.pool.putconn(conn)


@ttl_cache(ttl_seconds=300, ignore_kwargs=("client",), tags=("finance", "billing"))
def ar_trend_summary(client: Any = None, periods: int = 6) -> Dict[str, Any]:
    """Monthly billing trend for the last N months."""
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
    """Outstanding patient balances bucketed by age (days past billing date)."""
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
) -> List[Dict[str, Any]]:
    return []


def get_latest_gl_snapshot(client: Any = None) -> List[Dict[str, Any]]:
    return []


def latest_inventory_snapshot(client: Any = None) -> List[Dict[str, Any]]:
    return []


def inventory_by_skus(skus: List[str], client: Any = None) -> List[Dict[str, Any]]:
    return []
