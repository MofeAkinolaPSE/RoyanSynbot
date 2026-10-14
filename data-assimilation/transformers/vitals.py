"""Extract real vitals from Hope's `bmi_results` + `bmi_bp_results` tables
(staged as hope_bmi_results/hope_bmi_bp_results) -> royan_vitals.

Confirmed real by direct content check but genuinely noisy: each bmi_results
row carries up to 3 parallel reading slots (base, "1", "2" suffixed) --
only the base (unsuffixed) slot is used here as the representative reading,
not all three. Hope's own pre-computed `equal_value` (already Celsius) is
used for temperature rather than re-deriving from `temperature`+`myoption`,
since it's already correct (verified: 99 F + myoption "F" -> equal_value
"37.22 C" matches the real F->C conversion).

weight_result/height_result carry BOTH the numeric value and its unit in
one string, and the unit is NOT fixed per column -- observed both "27.27
Kg" and "211.2 Pounds" for weight_result, both "15.24 Cm" and "0 Cm" for
height_result -- parsed and converted to a canonical Kg/Cm value.

Hope's pre-computed `bmi`/`bsa` fields are dropped entirely: spot-checked
values are physiologically impossible (e.g. bmi="1174" alongside a 15cm
height/27kg weight combination) -- royan_vitals.bmi is left null rather
than loading a wrong number into a clinical table; the app can compute it
from height+weight if needed.

Clinical sanity ranges are applied per-field (not per-row) -- an
implausible respiration or spo2 value is dropped while the rest of a
row's real readings are kept, rather than discarding the whole row or
loading a value known to be wrong (e.g. one sampled row had spo2="160",
impossible for a 0-100% reading, sitting alongside an otherwise-plausible
temperature). systolic/diastolic/pulse of exactly 0 are Hope's
"not recorded" placeholder, not a real zero reading, and are dropped.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str

_NUM_UNIT_RE = re.compile(r"([\d.]+)\s*([A-Za-z]+)")

_WEIGHT_TO_KG = {"kg": 1.0, "kgs": 1.0, "pounds": 0.453592, "lbs": 0.453592, "oz": 0.0283495}
_HEIGHT_TO_CM = {"cm": 1.0, "inches": 2.54, "inch": 2.54, "feet": 30.48, "ft": 30.48}

_RANGES = {
    "temperature": (30.0, 45.0),
    "weight": (0.3, 300.0),
    "height": (20.0, 250.0),
    "bp_systolic": (40, 300),
    "bp_diastolic": (20, 200),
    "pulse": (20, 250),
    "respiratory_rate": (4, 80),
    "spo2": (30.0, 100.0),
}


def _in_range(field: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    lo, hi = _RANGES[field]
    return value if lo <= value <= hi else None


def _to_float(value: Any) -> Optional[float]:
    try:
        s = str(value).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return int(round(f)) if f is not None else None


def _parse_measurement(text: Optional[str], unit_map: Dict[str, float]) -> Optional[float]:
    """"27.27 Kg" -> 27.27; "211.2 Pounds" -> 95.8 (converted to Kg)."""
    if not text:
        return None
    m = _NUM_UNIT_RE.match(text.strip())
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    factor = unit_map.get(unit)
    if factor is None or value <= 0:
        return None
    return round(value * factor, 2)


def _parse_temperature_c(equal_value: Optional[str]) -> Optional[float]:
    if not equal_value:
        return None
    m = _NUM_UNIT_RE.match(equal_value.strip())
    if not m:
        return None
    return _to_float(m.group(1))


def transform(bmi_rows: List[Dict[str, Any]], bmi_bp_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bp_by_bmi_id: Dict[str, Dict[str, Any]] = {}
    for row in bmi_bp_rows:
        bmi_id = safe_str(row.get("bmi_result_id"))
        if bmi_id:
            bp_by_bmi_id[bmi_id] = row

    out = []
    for row in bmi_rows:
        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        recorded_at = safe_date(row.get("created_time"))
        if not recorded_at:
            continue

        temperature = _in_range("temperature", _parse_temperature_c(safe_str(row.get("equal_value"))))
        weight = _in_range("weight", _parse_measurement(safe_str(row.get("weight_result")), _WEIGHT_TO_KG))
        height = _in_range("height", _parse_measurement(safe_str(row.get("height_result")), _HEIGHT_TO_CM))
        respiratory_rate = _in_range("respiratory_rate", _to_int(row.get("respiration")))
        spo2 = _in_range("spo2", _to_float(row.get("spo")))

        bp_systolic = bp_diastolic = pulse = None
        bp = bp_by_bmi_id.get(ext_id)
        if bp:
            sys_val = _to_int(bp.get("systolic"))
            dia_val = _to_int(bp.get("diastolic"))
            pulse_val = _to_int(bp.get("pulse_text"))
            bp_systolic = _in_range("bp_systolic", sys_val) if sys_val else None
            bp_diastolic = _in_range("bp_diastolic", dia_val) if dia_val else None
            pulse = _in_range("pulse", pulse_val) if pulse_val else None

        if not any([temperature, weight, height, respiratory_rate, spo2, bp_systolic, bp_diastolic, pulse]):
            continue  # nothing real recorded on this row -- skip rather than insert an empty vitals row

        out.append({
            "_hope_patient_id":  hope_pid,
            "_recorded_at":      recorded_at,
            "temperature":       temperature,
            "weight":            weight,
            "height":            height,
            "respiratory_rate":  respiratory_rate,
            "spo2":              spo2,
            "bp_systolic":       bp_systolic,
            "bp_diastolic":      bp_diastolic,
            "pulse":             pulse,
            "recorded_by":       safe_str(row.get("created_by")),
            "recorded_at":       recorded_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
