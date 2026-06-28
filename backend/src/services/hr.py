from __future__ import annotations

from typing import Dict, Any
from typing import Any as DBClient
from ..db import db
from ..cache import ttl_cache


def _dt_to_str(val: object) -> str:
    """Coerce psycopg2 datetime/date to ISO string; passthrough for str/None."""
    if val is None:
        return ""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


MAX_ANALYTICS_ROWS = 3000


@ttl_cache(ttl_seconds=180, ignore_kwargs=("client",), tags=("staff", "hr_summary", "executive"))
def payroll_and_absence_summary(client: DBClient = db, periods: int = 3) -> Dict[str, Any]:
    """Compute HR analytics with deterministic formulas.

    - salary_total: sum(salary)
    - overtime_cost_total: sum(overtime_hours * overtime_rate)
    - overtime_pct_payroll: overtime_cost_total / (salary_total + overtime_cost_total)
    - avg_cost_per_employee: (salary_total + overtime_cost_total) / distinct_employees
    - absenteeism_trend: hours absent grouped by most recent N months
    """
    # Payroll — sourced from royan_payroll_records (HMS native)
    p = client.table("royan_payroll_records").select("staff_id,gross_salary,overtime_hours,overtime_rate").order("created_at", desc=True).limit(MAX_ANALYTICS_ROWS).execute()
    rows = p.data or []
    salary_total = sum(float(r.get("gross_salary") or 0) for r in rows)
    overtime_cost_total = sum(float(r.get("overtime_hours") or 0) * float(r.get("overtime_rate") or 0) for r in rows)
    employees = {r.get("staff_id") for r in rows if r.get("staff_id")}
    denom = max(1, len(employees))
    payroll_total = salary_total + overtime_cost_total
    overtime_pct = (overtime_cost_total / payroll_total) if payroll_total > 0 else 0.0
    avg_cost_per_emp = payroll_total / denom if denom > 0 else 0.0

    # Absences by month — sourced from royan_leave_requests (HMS native)
    a = client.table("royan_leave_requests").select("start_date,days_count").order("start_date", desc=True).limit(MAX_ANALYTICS_ROWS).execute()
    abs_rows = a.data or []
    buckets: Dict[str, float] = {}
    for r in abs_rows:
        d = _dt_to_str(r.get("start_date"))[:7]  # YYYY-MM
        if not d:
            continue
        buckets[d] = buckets.get(d, 0.0) + float(r.get("days_count") or 0) * 8  # days → hours
    # Most recent N periods
    periods_keys = sorted(buckets.keys(), reverse=True)[:periods]
    trend = [{"period": k, "hours": buckets[k]} for k in periods_keys]

    explain = {
        "salary_total": "sum(salary)",
        "overtime_cost_total": "sum(overtime_hours * overtime_rate)",
        "overtime_pct_payroll": "overtime_cost_total / (salary_total + overtime_cost_total)",
        "avg_cost_per_employee": "(salary_total + overtime_cost_total) / distinct_employees",
        "absenteeism_trend": "group by YYYY-MM: sum(hours)",
        "sources": ["royan_payroll_records", "royan_leave_requests"],
    }
    return {
        "salary_total": salary_total,
        "overtime_cost_total": overtime_cost_total,
        "overtime_pct_payroll": overtime_pct,
        "avg_cost_per_employee": avg_cost_per_emp,
        "absenteeism_trend": trend,
        "explain": explain,
    }
