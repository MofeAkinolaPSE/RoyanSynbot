"""Extract real radiology report content from Hope's `radiology_results`
table (staged as hope_radiology_results) -> denormalized columns on the
already-loaded royan_radiology_orders (report/impression/radiologist_id/
reported_at). royan_radiology_results (migration 137) is confirmed dead --
this pipeline correctly targets the real, live schema instead (see
migration 163's own comment and migration 139's report columns).

radiology_test_order_id links directly to the already-loaded
royan_radiology_orders.external_id -- a reliable direct match, not the
nearest-timestamp guess needed for notes/discharge records (Hope's
radiology_reports table is redundant with this one for our purposes: it's
a thin index row pointing back at the same radiology_result_id/
radiology_test_order_id with no additional content, so it's not used here).

Hope's `note` field is a full radiology report written as basic HTML
(<p>/<strong>/<br /> tags, &nbsp; entities) -- stripped to plain text with
paragraph breaks preserved, since the live report field is plain text.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from transformers._helpers import safe_date, safe_str

_TAG_RE = re.compile(r"<[^>]+>")
_NBSP_RE = re.compile(r"&nbsp;", re.IGNORECASE)


def _html_to_text(html: str) -> str:
    text = _NBSP_RE.sub(" ", html)
    # paragraph/line-break tags become real newlines before tags are stripped
    text = re.sub(r"</p>|<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    # collapse the \r\n litter and excess blank lines Hope's editor left behind
    lines = [ln.strip() for ln in text.replace("\\r\\n", "\n").splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _normalize_text(text: str) -> str:
    """img_impression (unlike note) is never HTML, but still carries Hope's
    literal "\\r\\n" escape sequences rather than real line breaks."""
    lines = [ln.strip() for ln in text.replace("\\r\\n", "\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        order_ext_id = safe_str(row.get("radiology_test_order_id"))
        note = safe_str(row.get("note"))
        impression = safe_str(row.get("img_impression"))
        if impression:
            impression = _normalize_text(impression)
        if not order_ext_id or not (note or impression):
            continue

        reported_at = safe_date(row.get("result_publish_date")) or safe_date(row.get("modify_time"))

        out.append({
            "_hope_order_ext_id": order_ext_id,
            "_hope_radiologist_id": safe_str(row.get("modified_by")) or safe_str(row.get("user_id")),
            "report":            _html_to_text(note) if note else None,
            "impression":        impression,
            "reported_at":       reported_at,
        })
    return out
