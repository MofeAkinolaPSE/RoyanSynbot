"""Extract real ward admit/discharge history from Hope's `ward_patients`
table (staged as hope_ward_patients) -> royan_ward_stay_history.

Resolves ward_id/room_id/bed_id against Hope's own `wards`/`rooms`/`beds`
reference tables to real names (e.g. "First Floor", "Room101") -- confirmed
5 of Hope's 5 real wards exactly name-match the already-seeded royan_wards
rows, so ward_name is looked up against royan_wards by name at load time
(not here, this module has no DB access); room/bed stay as descriptive
text since the live system's bed configuration (24 beds) is far smaller
than Hope's historical one (185 beds) -- forcing a bed-level FK match
would be wrong more often than right.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _build_lookups(wards_raw: List[Dict[str, Any]], rooms_raw: List[Dict[str, Any]], beds_raw: List[Dict[str, Any]]):
    ward_name_by_id = {}
    for r in wards_raw:
        wid = safe_str(r.get("id"))
        name = safe_str(r.get("name"))
        if wid and name:
            ward_name_by_id[wid] = name

    room_by_id = {}
    for r in rooms_raw:
        rid = safe_str(r.get("id"))
        name = safe_str(r.get("name"))
        if rid and name:
            room_by_id[rid] = name

    bed_by_id = {}
    for r in beds_raw:
        bid = safe_str(r.get("id"))
        bedno = safe_str(r.get("bedno"))
        if bid and bedno:
            bed_by_id[bid] = bedno

    return ward_name_by_id, room_by_id, bed_by_id


def transform(
    raw_rows: List[Dict[str, Any]],
    wards_raw: List[Dict[str, Any]],
    rooms_raw: List[Dict[str, Any]],
    beds_raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ward_name_by_id, room_by_id, bed_by_id = _build_lookups(wards_raw, rooms_raw, beds_raw)

    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue

        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        admitted_at = safe_date(row.get("in_date"))
        if not ext_id or not hope_pid or not admitted_at:
            continue

        ward_id_raw = safe_str(row.get("ward_id"))
        room_id_raw = safe_str(row.get("room_id"))
        bed_id_raw = safe_str(row.get("bed_id"))

        room_name = room_by_id.get(room_id_raw) if room_id_raw else None
        bed_label = bed_by_id.get(bed_id_raw) if bed_id_raw else None

        out.append({
            "_hope_patient_id":  hope_pid,
            "_ward_name":        ward_name_by_id.get(ward_id_raw) if ward_id_raw else None,
            "ward_name":         ward_name_by_id.get(ward_id_raw) if ward_id_raw else None,
            "room_name":         room_name,
            "bed_label":         bed_label,
            "admitted_at":       admitted_at,
            "discharged_at":     safe_date(row.get("out_date")),
            "is_discharged":     safe_str(row.get("is_discharge")) == "1",
            "readmitted":        bool(safe_str(row.get("readmitted"))),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
