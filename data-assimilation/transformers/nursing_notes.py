"""Extract real nursing documentation from Hope's `nurse_notes` (SOAP-shaped,
1,558 rows) and `shift_notes` (flat free-text shift-handover notes, 68,196
rows -- the primary volume) tables -> royan_encounter_notes
(note_type='nursing'), reusing loaders.db_loader.load_encounter_notes
unmodified (same payload shape as transformers/hope_notes.py).

Same "no explicit per-note encounter link" situation as hope_notes.py:
neither table has a usable visit/encounter FK, so both reuse the exact same
nearest-created_at-timestamp resolution the loader already implements
(_hope_patient_id + _note_at).

shift_notes.pre_opt content quality was checked at scale before committing
to load it (random samples spanning the full 2016-2025 date range, both
sign_flag values) and confirmed to be overwhelmingly real, specific nursing
shift-handover documentation -- not test/demo artifacts like the garbage
found in Hope's Order Set data elsewhere in this project. sign_flag does
NOT reliably separate real from test content (both values showed real
content on random sampling; an early non-random sample of the first ~5 rows
misleadingly suggested otherwise), so it is not used as a filter here --
every row with a real patient_id and non-empty pre_opt is loaded.

external_id is prefixed per source table (nurse_note:/shift_note:) because
royan_encounter_notes' (external_source, external_id) key is shared with
hope_notes.py's doctor notes (up to id 245849) and both nursing tables
independently start their own id sequences at 1 -- an unprefixed id here
would collide with and silently overwrite an unrelated already-loaded note,
the same class of bug caught and fixed in pharmacy_purchase_batches.py
earlier in this project.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def transform_nurse_notes(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """nurse_notes: SOAP-shaped (subjective/objective/assessment/plan),
    same content-synthesis approach as hope_notes.py."""
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}
        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        subjective = safe_str(raw.get("subjective"))
        objective = safe_str(raw.get("objective"))
        assessment = safe_str(raw.get("assessment"))
        plan = safe_str(raw.get("plan"))
        complaints = safe_str(raw.get("complaints"))
        if not any((subjective, objective, assessment, plan, complaints)):
            continue

        note_at = safe_date(raw.get("date_of_seen"))
        if not note_at:
            continue

        parts = []
        if complaints:
            parts.append(f"Complaints: {complaints}")
        for label, val in (("Subjective", subjective), ("Objective", objective),
                            ("Assessment", assessment), ("Plan", plan)):
            if val:
                parts.append(f"{label}: {val}")
        content = "\n".join(parts)

        out.append({
            "_hope_patient_id":  hope_pid,
            "_note_at":          note_at,
            "note_type":         "nursing",
            "content":           content,
            "subjective":        subjective,
            "objective":         objective,
            "assessment":        assessment,
            "plan":              plan,
            "icd10_codes":       None,
            "author_name":       None,
            "created_at":        note_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       f"nurse_note:{ext_id}",
        })
    return out


def transform_shift_notes(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """shift_notes: flat free-text nursing shift-handover documentation
    (pre_opt) -- the primary volume of real nursing notes."""
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}
        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        content = safe_str(raw.get("pre_opt"))
        if not ext_id or not hope_pid or not content:
            continue

        note_at = safe_date(raw.get("date_of_seen"))
        if not note_at:
            continue

        out.append({
            "_hope_patient_id":  hope_pid,
            "_note_at":          note_at,
            "note_type":         "nursing",
            "content":           content,
            "subjective":        None,
            "objective":         None,
            "assessment":        None,
            "plan":              None,
            "icd10_codes":       None,
            "author_name":       None,
            "created_at":        note_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       f"shift_note:{ext_id}",
        })
    return out
