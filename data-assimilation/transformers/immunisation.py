"""Extract real vaccine administration history from Hope's `imunizations`
table (staged as hope_imunizations -- note the source table's own typo,
not this file's) -> royan_immunisation (migration 148, retrofitted with
external tracking by migration 187).

Uses the typo'd `imunizations` table (~18K rows), not its correctly-spelled
257-row sibling `immunizations` -- confirmed via AUTO_INCREMENT that the
typo'd table is the real, primary one; the correctly-spelled table is a
much smaller variant (not yet content-verified, deprioritized given the
typo'd table's clear volume advantage).
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, normalize_text, safe_date, safe_str


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        if safe_str(raw.get("is_deleted")) == "1":
            continue

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        vaccine_name = safe_str(raw.get("vaccine_type"))
        if not ext_id or not hope_pid or not vaccine_name:
            continue

        date_given = safe_date(raw.get("date"))
        if not date_given:
            continue

        notes_parts = [p for p in (safe_str(raw.get("admin_note")), safe_str(raw.get("comments"))) if p]

        out.append({
            "_hope_patient_id":  hope_pid,
            "vaccine_name":      vaccine_name,
            "date_given":        date_given,
            "batch_number":      safe_str(raw.get("lot_number")),
            "site":              safe_str(raw.get("admin_site")),
            "administered_by":   safe_str(raw.get("provider")),
            "next_due_date":     safe_date(raw.get("due_date")),
            "notes":             normalize_text("; ".join(notes_parts)) if notes_parts else None,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
