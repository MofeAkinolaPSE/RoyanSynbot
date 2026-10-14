"""Extract real ward/ICU progress notes from Hope's `progresstbls` table
(staged as hope_progresstbls) -> royan_encounter_notes (note_type='progress').
Reuses load_encounter_notes unmodified -- same payload shape as
transformers/hope_notes.py (nearest-encounter-timestamp resolution,
author_id/author_name are free text so Hope's raw seen_by id is stored
as-is, matching the precedent set for doctor notes).

Confirmed real by direct content check: id=1's subjective field is literal
setup/test filler ("Test Drm Test Subjective 1 Test Drm Test Subjective 1
test details test result... Test Drm template.") -- filtered out by the
"Test Drm" marker (the same DRM-Nigeria-vendor test-seed pattern found
elsewhere in this dump, e.g. persons.last_name="Drmpatient"). The bulk of
rows are genuine clinical documentation (e.g. id=2: "Doing well. Complains
of incisional pain but otherwise doing well" / "NAD. Abdomen soft ND. NT.
Dressing clean/dry and intact...").

Embedded vitals (temp/bp/hr/rr/spo2/weight) are free-text strings (e.g.
"110/60 mm of Hg", "140/min") rather than clean numerics -- deliberately
NOT parsed here. bmi_results/bmi_bp_results are a much larger, cleanly
tabular vitals source and are backfilled separately (transformers/vitals.py).

The formal sign/unsign/addendum audit trail (reason_to_unsign, unsign_by,
unsign_date, addendum, addendum_by, addendum_date) is historical dead data
in this migration (not a live editable workflow) -- addendum text, when
present, is appended to `plan` as a dated note rather than modeled as its
own live amendment feature.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, normalize_text, safe_date, safe_str

_TEST_MARKER = "test drm test"


def _has_content(raw: Dict[str, Any]) -> bool:
    return any(safe_str(raw.get(f)) for f in ("subjective", "objective", "assessment", "plan", "complaints"))


def _is_test_row(raw: Dict[str, Any]) -> bool:
    for f in ("subjective", "objective", "assessment", "plan", "complaints"):
        v = (safe_str(raw.get(f)) or "").lower()
        if _TEST_MARKER in v:
            return True
    return False


def _build_content(subjective: str, objective: str, assessment: str, plan: str, complaints: str) -> str:
    parts = []
    if complaints:
        parts.append(f"Complaints: {complaints}")
    for label, v in (("Subjective", subjective), ("Objective", objective),
                      ("Assessment", assessment), ("Plan", plan)):
        if v:
            parts.append(f"{label}: {v}")
    return "\n".join(parts)


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        if safe_str(raw.get("is_deleted")) == "1":
            continue

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue
        if not _has_content(raw) or _is_test_row(raw):
            continue

        note_at = safe_date(raw.get("date_of_seen"))
        if not note_at:
            continue

        subjective = normalize_text(safe_str(raw.get("subjective"))) or ""
        objective = normalize_text(safe_str(raw.get("objective"))) or ""
        assessment = normalize_text(safe_str(raw.get("assessment"))) or ""
        plan = normalize_text(safe_str(raw.get("plan"))) or ""
        complaints = normalize_text(safe_str(raw.get("complaints"))) or ""

        addendum = normalize_text(safe_str(raw.get("addendum"))) or ""
        if addendum:
            addendum_date = safe_str(raw.get("addendum_date")) or ""
            plan = f"{plan}\n\n[Addendum{' ' + addendum_date if addendum_date else ''}]: {addendum}".strip()

        out.append({
            "_hope_patient_id":  hope_pid,
            "_note_at":          note_at,
            "note_type":         "progress",
            "content":           _build_content(subjective, objective, assessment, plan, complaints),
            "subjective":        (f"Complaints: {complaints}\n{subjective}" if complaints else subjective) or None,
            "objective":         objective or None,
            "assessment":        assessment or None,
            "plan":              plan or None,
            "author_id":         safe_str(raw.get("seen_by")) or None,
            "created_at":        note_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
