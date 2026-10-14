"""Extract Hope's smart_phrases/smart_phrase_multiple -> royan_smart_phrases +
royan_smart_phrase_options -- a third, separate dot-phrase/macro system,
distinct from the note_templates (migration 181) and order_sets (migration
179) families already loaded. Invoked by typing a shorthand trigger (e.g.
"NEXANKLES") rather than picking from a section dropdown.

Confirmed real by direct content check: id=1 ("DRUGTEST") is a leftover
setup/test row (matches this project's now-established pattern of a small
number of test rows seeded at the start of nearly every Hope table) --
filtered out by name. The bulk of rows are genuine clinical exam-language
templates (e.g. id=2 "NEXANKLES": "Ankle exam - {side:15002::both sides}
normal; full range of motion...").

doctor_id='0' or unset means shared/system-scope; a real Hope staff id means
personally authored -- resolved against royan_staff via _staff_id_by_external
at load time (not here, since this module has no DB access).
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from transformers._helpers import EXTERNAL_SOURCE, safe_str

_TEST_PHRASE_NAMES = {"DRUGTEST", "TEST", "TESTPHRASE"}


def transform_smart_phrases(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        phrase = safe_str(row.get("phrase"))
        phrase_text = safe_str(row.get("phrase_text"))
        ext_id = safe_str(row.get("id"))
        if not phrase or not phrase_text or not ext_id:
            continue
        if phrase.upper() in _TEST_PHRASE_NAMES:
            continue

        doctor_hope_id = safe_str(row.get("doctor_id"))
        is_shared = not doctor_hope_id or doctor_hope_id == "0"

        out.append({
            "_hope_doctor_id":  None if is_shared else doctor_hope_id,
            "phrase":           phrase,
            "synonyms":         safe_str(row.get("synonyms")) or None,
            "phrase_text":      phrase_text,
            "is_nursing":       safe_str(row.get("is_nursing")) == "1",
            "is_shared":        is_shared,
            "department":       safe_str(row.get("department_id")) or None,
            "is_active":        True,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def valid_phrase_ids(payloads: List[Dict[str, Any]]) -> Set[str]:
    return {p["external_id"] for p in payloads}


def transform_smart_phrase_options(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """smart_phrase_multiple.phrase_id is NOT a smart_phrases.id FK -- it is
    the {token:id::default} placeholder id embedded inside a phrase_text, and
    one option list can be shared by several different phrases. Kept as a
    standalone token-keyed lookup rather than forced onto a single phrase.
    """
    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_rows:
        token_id = safe_str(row.get("phrase_id"))
        list_name = safe_str(row.get("list_name"))
        option_text = safe_str(row.get("list_content"))
        ext_id = safe_str(row.get("id"))
        if not token_id or not list_name or not option_text or not ext_id:
            continue

        key = f"{token_id}:{list_name}"
        sort_counters[key] = sort_counters.get(key, 0) + 1
        out.append({
            "token_id":         token_id,
            "list_name":        list_name,
            "option_text":      option_text,
            "sort_order":       sort_counters[key],
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out
