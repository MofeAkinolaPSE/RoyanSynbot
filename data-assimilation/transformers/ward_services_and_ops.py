"""Phase A3 ("finish the job") transformers for Hope's remaining real
ward/operational tables:

  ward_patient_services -> royan_ward_service_charges   (34,149)
  patient_documents     -> royan_patient_documents      (9,192)
  direct_consumptions   -> royan_ward_consumption       (8,972 w/ patient)
  doctor_chambers       -> royan_doctor_schedule_blocks (768)
  medication_administering_records -> royan_medication_administration (109)
  patient_profiles      -> royan_encounter_notes        (3,365 real notes)

All confirmed real by direct content sampling. Hope's `guarantors`/
`guardians` were checked the same way and found to be entirely empty
shells (0 of ~31,000 rows carry a name) -- no transformer built for them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, normalize_text, safe_date, safe_str


def _num(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        return round(float(s), 2) if s and s.lower() != "none" else None
    except (ValueError, TypeError):
        return None


def _int(value: Any) -> Optional[int]:
    n = _num(value)
    return int(round(n)) if n is not None else None


def _flag(value: Any) -> bool:
    return safe_str(value) == "1"


def transform_ward_service_charges(
    raw_rows: List[Dict[str, Any]],
    wards_raw: List[Dict[str, Any]],
    rooms_raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ward_by_id = {safe_str(r.get("id")): safe_str(r.get("name")) for r in wards_raw if r.get("id")}
    room_by_id = {safe_str(r.get("id")): safe_str(r.get("name")) for r in rooms_raw if r.get("id")}

    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        out.append({
            "_hope_patient_id": hope_pid,
            "ward_name":        ward_by_id.get(safe_str(row.get("ward_id"))),
            "room_name":        room_by_id.get(safe_str(row.get("room_id"))),
            "service_date":     safe_date(row.get("date")),
            "amount":           _num(row.get("amount")),
            "paid_amount":      _num(row.get("paid_amount")),
            "paid_by_cash":     _num(row.get("paid_by_cash")),
            "paid_by_card":     _num(row.get("paid_by_card")),
            "units":            _num(row.get("unit")),
            "is_capitation":    _flag(row.get("is_capitation")),
            "tariff_ref":       safe_str(row.get("tariff_list_id")),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def transform_patient_documents(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        out.append({
            "_hope_patient_id": hope_pid,
            "filename":         safe_str(row.get("filename")),
            "mime_type":        safe_str(row.get("type")),
            "size_bytes":       _int(row.get("size")),
            "description":      safe_str(row.get("document_description")),
            "comment":          normalize_text(safe_str(row.get("comment"))),
            "document_date":    safe_date(row.get("date")),
            # Hope's binary `file` column is not carried across in this
            # migration -- this row is an index entry, not the document.
            "is_migrated":      False,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def transform_ward_consumption(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue
        qty = _num(row.get("issued_qty"))
        if not qty or qty <= 0:
            continue

        out.append({
            "_hope_patient_id": safe_str(row.get("patient_id")) or None,
            "_hope_item_id":    safe_str(row.get("product_id")) or None,
            "product_ref":      safe_str(row.get("product_id")),
            "issued_qty":       qty,
            "issued_at":        safe_date(row.get("create_time")),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def transform_doctor_schedule_blocks(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue

        out.append({
            "_hope_doctor_id": safe_str(row.get("doctor_id")) or None,
            "doctor_ref":      safe_str(row.get("doctor_id")),
            "purpose":         safe_str(row.get("purpose")),
            "starts_at":       safe_date(row.get("starttime")),
            "ends_at":         safe_date(row.get("endtime")),
            "start_time":      safe_str(row.get("start_time")),
            "end_time":        safe_str(row.get("end_time")),
            "is_blocked":      _flag(row.get("is_blocked")),
            "is_all_day":      _flag(row.get("is_all_day_event")),
            "is_recurring":    _flag(row.get("is_recurring")),
            "external_source": EXTERNAL_SOURCE,
            "external_id":     ext_id,
        })
    return out


def transform_medication_administration(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        out.append({
            "_hope_patient_id": hope_pid,
            "performed_at":     safe_date(row.get("performed_datetime")),
            "performed_by":     safe_str(row.get("performed_by")),
            "pain_intensity":   _int(row.get("pain_intensity")),
            "not_given":        _flag(row.get("not_given")),
            "is_signed":        _flag(row.get("is_signed")),
            # Hope encodes the administration detail as an undocumented
            # pipe-delimited blob ("1||250||18||1||2"). No key exists in
            # the dump to decode it -- kept verbatim rather than guessed at.
            "nurse_data":       safe_str(row.get("nursedata")),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def transform_patient_profile_notes(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """patient_profiles.other_notes holds real nursing/clinical free text
    ("2nd dose of i/m Arteether 40mg given.", "DRESSING DONE", "FOLLOWUP
    ANTENATAL EXERCISE COMMENCED") on 3,365 of 9,642 rows. Routed to
    royan_encounter_notes via load_encounter_notes, same payload shape as
    hope_notes.py / nursing_notes.py. external_id prefixed to avoid
    colliding with the other note sources sharing that key space.
    """
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        note = normalize_text(safe_str(row.get("other_notes")))
        if not ext_id or not hope_pid or not note:
            continue

        note_at = safe_date(row.get("create_time"))
        if not note_at:
            continue

        out.append({
            "_hope_patient_id": hope_pid,
            "_note_at":         note_at,
            "note_type":        "nursing",
            "content":          note,
            "author_id":        safe_str(row.get("created_by")) or None,
            "created_at":       note_at,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      f"patient_profile:{ext_id}",
        })
    return out
