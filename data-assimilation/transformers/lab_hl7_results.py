"""Extract real per-analyte lab result rows from Hope's
`laboratory_hl7_results` table (staged as `hope_lab_hl7_results`) ->
royan_lab_results.

This is a different, much more granular source than transformers/lab_results.py
(which reads `laboratory_results`, the HL7 order-level shell -- one row per
order, often empty). `laboratory_hl7_results` is the real per-parameter
result set: a single CBC-style panel order produces one row per analyte
(hemoglobin, WBC count, platelets, ...), each carrying its own value/unit/
range/abnormal_flag. It carries `laboratory_test_order_id` directly
(confirmed via schema inspection), matching royan_lab_orders.external_id --
no need to route through laboratory_results at all.

`laboratory_parameters` (staged as `hope_lab_parameters`) is the id -> name
lookup for `laboratory_parameter_id`, passed in as `parameter_catalog`.

royan_lab_results.lab_order_id has no uniqueness constraint, so multiple
rows per order (one per analyte) is exactly what the schema already
supports -- this was previously underused because transformers/lab_results.py
had no external_id to upsert against safely. This transform uses the HL7
row's own id (migration 177), so every analyte gets its own idempotent row.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow

# Hope stores abnormal_flag as free text; these are the values actually seen
# in HL7-style exports (H/L/HH/LL/A/AA plus a few human-typed variants).
_CRITICAL_FLAGS = {"hh", "ll", "aa", "critical", "panic"}
_ABNORMAL_FLAGS = {"h", "l", "a", "high", "low", "abnormal", "positive", "pos"}
_NORMAL_FLAGS = {"n", "normal", "negative", "neg"}


def _interpretation(abnormal_flag: Optional[str], status: Optional[str]) -> Optional[str]:
    flag = (abnormal_flag or "").strip().lower()
    if flag in _CRITICAL_FLAGS:
        return "critical"
    if flag in _ABNORMAL_FLAGS:
        return "abnormal"
    if flag in _NORMAL_FLAGS:
        return "normal"
    status_l = (status or "").strip().lower()
    if "critical" in status_l or "panic" in status_l:
        return "critical"
    return None


def transform(
    raw_rows: List[Dict[str, Any]],
    parameter_catalog: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    parameter_catalog = parameter_catalog or {}
    out = []

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id"))
        lab_order_ext_id = safe_str(raw.get("laboratory_test_order_id"))
        if not ext_id or not lab_order_ext_id:
            continue

        result_value = safe_str(raw.get("result")) or safe_str(raw.get("sn_value"))
        observations = safe_str(raw.get("observations"))
        if not result_value and not observations:
            continue  # empty HL7 shell row, no actual result content

        param_id = safe_str(raw.get("laboratory_parameter_id"))
        param = parameter_catalog.get(param_id, {}) if param_id else {}
        param_name = param.get("name")
        unit = safe_str(raw.get("uom")) or safe_str(raw.get("unit")) or param.get("unit")

        result_summary = (
            f"{param_name}: {result_value} {unit}".strip()
            if param_name and result_value
            else (result_value or observations)
        )

        reference_range = safe_str(raw.get("range"))
        abnormal_flag = safe_str(raw.get("abnormal_flag"))
        status = safe_str(raw.get("status"))
        interpretation = _interpretation(abnormal_flag, status)

        # date_time_of_observation is a free-text varchar in Hope (unverified
        # format -- possibly compact HL7 numeric, not a native datetime) and
        # empty in practice; modify_time/create_time are native datetime
        # columns but also empty in practice (confirmed by direct sampling:
        # 0% populated). `modified` is the only one that's actually
        # populated (100% in a 20k-row sample) -- listed first for that
        # reason, with the empty-in-practice columns kept as a defensive
        # fallback in case that changes across the full dataset.
        resulted_at = (
            safe_date(raw.get("modified"))
            or safe_date(raw.get("modify_time"))
            or safe_date(raw.get("create_time"))
            or utcnow()
        )

        result_data: Dict[str, str] = {}
        for key, val in (
            ("parameter", param_name),
            ("result", result_value),
            ("uom", unit),
            ("range", reference_range),
            ("abnormal_flag", abnormal_flag),
            ("status", status),
            ("observations", observations),
            ("observed_at_raw", safe_str(raw.get("date_time_of_observation"))),
        ):
            if val:
                result_data[key] = val

        out.append({
            "_hope_lab_order_ext_id": lab_order_ext_id,
            "result_data":            result_data if result_data else None,
            "result_summary":         result_summary,
            "reference_range":        reference_range,
            "interpretation":         interpretation,
            "resulted_by":            "hope_ingest",
            "resulted_at":            resulted_at,
            "is_critical":            interpretation == "critical",
            "notes":                  None,
            "external_source":        EXTERNAL_SOURCE,
            "external_id":            ext_id,
            "external_updated_at":    utcnow(),
        })

    return out
