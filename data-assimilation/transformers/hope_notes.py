"""Extract real clinical notes from Hope's `notes` table (staged as
`hope_notes`) -> royan_encounter_notes.

Encounter linkage: Hope's `notes.visitid` (the field name that looks like
the obvious FK) is a pipe-delimited checkbox multi-select and is empty on
100% of the 245,849 rows in this dump -- confirmed by direct inspection, not
assumed. `note_diagnosis` (the other candidate link, via note_id) turns out
to be a static ICD-10 reference/lookup table for the diagnosis-picker UI,
not a per-note junction table -- 0 of 212,381 rows have diagnosis_id
populated, and only 640 even have note_id (all pointing at the same single
demo note). Neither field is usable.

So there is no explicit per-note encounter link in the source data at all.
The loader instead resolves each note to its patient's encounter with the
closest created_at to the note's own create_time (a mechanical nearest-
timestamp match, not a content/semantic guess -- see
scripts/dedupe_legacy_encounters.py's docstring for why a semantic
chief_complaint-vs-note-text approach was tried for a different problem and
matched ~0% of real multi-visit patients; nearest-timestamp doesn't have
that ambiguity problem since it doesn't need to interpret meaning). A note
with no resolvable patient or whose patient has zero encounters is skipped,
not force-attached to a guess.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow

_CONTENT_FIELDS = ("subject", "object", "assis", "plan", "note", "title", "cc")


def _has_content(raw: Dict[str, Any]) -> bool:
    return any(safe_str(raw.get(f)) for f in _CONTENT_FIELDS)


def _build_content(raw: Dict[str, Any]) -> str:
    """royan_encounter_notes.content is NOT NULL -- synthesize a readable
    fallback from the SOAP fields when Hope's own free-text `note`/`title`
    are empty (the common case for this SOAP-shaped variant of the table)."""
    note = safe_str(raw.get("note"))
    if note:
        return note
    title = safe_str(raw.get("title"))
    parts = []
    for label, field in (("Subjective", "subject"), ("Objective", "object"),
                          ("Assessment", "assis"), ("Plan", "plan")):
        v = safe_str(raw.get(field))
        if v:
            parts.append(f"{label}: {v}")
    body = "\n".join(parts)
    if title and body:
        return f"{title}\n{body}"
    return title or body or ""


def _icd_codes(raw: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    for field in ("icd", "icd_record"):
        v = safe_str(raw.get(field))
        if not v:
            continue
        for tok in v.replace(";", ",").split(","):
            tok = tok.strip()
            if tok and tok not in codes:
                codes.append(tok)
    return codes


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue
        if not _has_content(raw):
            continue

        note_at = safe_date(raw.get("create_time")) or safe_date(raw.get("note_date"))
        if not note_at:
            continue

        has_soap = any(safe_str(raw.get(f)) for f in ("subject", "object", "assis", "plan"))

        out.append({
            "_hope_patient_id":  hope_pid,
            "_note_at":          note_at,
            "note_type":         "soap" if has_soap else "general",
            "content":           _build_content(raw),
            "subjective":        safe_str(raw.get("subject")),
            "objective":         safe_str(raw.get("object")),
            "assessment":        safe_str(raw.get("assis")),
            "plan":              safe_str(raw.get("plan")),
            "icd10_codes":       _icd_codes(raw) or None,
            "author_name":       None,  # Hope's signed_by is a raw numeric staff id;
                                          # not resolved in this pass — see follow-up note
            "created_at":        note_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
