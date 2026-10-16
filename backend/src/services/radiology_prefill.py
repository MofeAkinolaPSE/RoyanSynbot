"""What the Scancare report form starts with, so the radiologist only edits what is different about this patient.

Scancare writes the same layout for each kind of study (INDICATION / TECHNIQUE / FINDINGS organ by organ /
IMPRESSION) - 41,000 reports in Hope across 170 study types. For a new study the form is pre-filled with Scancare's
own standard wording for that exact study: its most recent normal report of that type (Scancare's own reports first,
then Hope's), else the most recent report of that type, else the canned library for the modality. Two safeguards:

  - every measurement is blanked to ___ (134.1MM -> ___MM, 91.1X38.4MM -> ___X___MM, FHR= 148BPM -> ___BPM) so
    another patient's numbers can never end up on this report;
  - the INDICATION is this order's clinical indication, not the earlier patient's.

Also returned: Hope's phrase snippets for this exam type (FINDINGS / OPINIONS) for one-click insertion, and the canned
templates for the modality.
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from src.fin.db import q, q1, tx

_UNIT = r"(?:MM|CM3|CM|MLS?|BPM|WEEKS?|WKS?|DAYS?|%|MMHG|KGS?|G\b|CC|HU)"
_MEASURE = re.compile(rf"(?<![A-WYZ0-9.])\d+(?:\.\d+)?(?=\s*(?:X\s*\d+(?:\.\d+)?\s*)*{_UNIT})", re.I)
_INDICATION = re.compile(r"^\s*(?:(?:CLINICAL\s+)?INDICATIONS?|CLINICAL\s+(?:HISTORY|DETAILS?|INFORMATION)|HISTORY)\s*:?\s*(.*)$", re.I)
_DATE = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")
_PERSONAL = re.compile(r"^(\s*(?:GENDER|SEX|EDD|LMP|NAME|AGE)\s*[:=]\s*)(.*?)(\s*\(DD/MM/YYYY\))?\s*$", re.I)
_HEADER = re.compile(r"^\s*(?:TECHNIQUE|FINDINGS?|IMPRESSIONS?|OPINIONS?|CONCLUSIONS?|COMMENTS?|REPORT|PROCEDURE|"
                     r"[A-Z][A-Z /&()\-]{2,40}:)\s*", re.I)


def blank_measurements(text: str) -> str:
    """Another patient's numbers, dates and personal details never carry over: measurements, dates, and the
    GENDER / EDD / LMP / AGE lines become ___."""
    text = _MEASURE.sub("___", text)
    text = _DATE.sub("___", text)
    return "\n".join(_PERSONAL.sub(lambda m: m.group(1) + "___" + (m.group(3) or ""), ln) for ln in text.split("\n"))


def with_indication(text: str, indication: Optional[str]) -> str:
    """Replace the INDICATION block (the line and its continuation lines up to the next heading) with this order's."""
    lines = text.split("\n")
    out: List[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        m = _INDICATION.match(lines[i]) if not replaced else None
        if m:
            replaced = True
            out.append("INDICATION:")
            out.append((indication or "___").upper())
            i += 1
            while i < len(lines) and lines[i].strip() and not _HEADER.match(lines[i]):
                i += 1                                   # the earlier patient's indication lines
            continue
        out.append(lines[i])
        i += 1
    if not replaced and indication:
        out.insert(0, f"INDICATION:\n{indication.upper()}")
    return "\n".join(out)


def _clean(text: Optional[str], indication: Optional[str]) -> str:
    t = html.unescape(text or "").replace("\r\n", "\n").strip()
    return with_indication(blank_measurements(t), indication)


def report_template(order_id: int) -> Dict[str, Any]:
    with tx() as conn:
        o = q1(conn, """SELECT o.id, o.test_name, o.modality, o.clinical_indication, o.radiology_catalog_id, c.external_id AS hope_exam
                        FROM royan_radiology_orders o
                        LEFT JOIN royan_radiology_catalog c ON c.id::text = o.radiology_catalog_id::text
                        WHERE o.id=%s""", (order_id,))
        if not o:
            raise LookupError("Scan order not found")
        prev = q1(conn, r"""SELECT id, report, impression, reported_at, external_source
                           FROM royan_radiology_orders
                           WHERE upper(test_name) = upper(%s) AND id <> %s AND COALESCE(report, '') <> ''
                           ORDER BY
                             -- a complete, structured report (not a two-line note) ...
                             (length(report) >= 300 AND report ~* 'FINDINGS') DESC,
                             -- ... of a NORMAL study: its conclusion (the impression, or the text after IMPRESSION /
                             -- CONCLUSION / OPINION in the report) opens with "normal" - the standard wording, with
                             -- nothing about an earlier patient's disease to undo
                             (left(trim(COALESCE(NULLIF(trim(impression), ''),
                                   substring(report from '(?:IMPRESSION|CONCLUSION|OPINION)S?\s*:?\s*(.*)$'), '')), 60)
                                ~* '^\W*(\d\W*)?(essentially\s+|grossly\s+|sonographically\s+)?(normal|unremarkable|no\s+(significant\s+)?(abnormality|abnormalities)|live,?\s+(singleton|twin))'
                              AND COALESCE(NULLIF(trim(impression), ''),
                                   substring(report from '(?:IMPRESSION|CONCLUSION|OPINION)S?\s*:?\s*(.*)$'), '') !~* 'abnormal(?!it)') DESC,
                             (external_source IS NULL) DESC, COALESCE(reported_at, ordered_at) DESC NULLS LAST
                           LIMIT 1""", (o["test_name"] or "", order_id))
        phrases = q(conn, """SELECT t.section, x.text FROM royan_radiology_report_templates t
                             JOIN royan_radiology_report_template_texts x ON x.template_id = t.id
                             WHERE t.is_active AND t.exam_type_ref = %s ORDER BY t.section, x.sort_order""",
                    (str(o["hope_exam"] or o["radiology_catalog_id"] or ""),))
        canned = q(conn, """SELECT id, variant_name FROM royan_report_templates
                            WHERE is_active AND (%s::text IS NULL OR lower(modality) = lower(%s::text)) ORDER BY variant_name LIMIT 50""",
                   (o["modality"], o["modality"]))
    out: Dict[str, Any] = {"order_id": order_id, "test_name": o["test_name"], "phrases": phrases,
                           "canned": canned, "source": "none", "report": "", "impression": ""}
    if prev:
        out.update({
            "source": "scancare_previous" if not prev["external_source"] else "hope_previous",
            "based_on": f"Scancare's standard {o['test_name']} report (measurements blanked - fill in this patient's)",
            "report": _clean(prev["report"], o["clinical_indication"]),
            "impression": blank_measurements(html.unescape(prev["impression"] or "").replace("\r\n", "\n").strip()),
        })
    elif o["clinical_indication"]:
        out["report"] = f"INDICATION:\n{o['clinical_indication'].upper()}\nTECHNIQUE:\n___\nFINDINGS:\n___"
        out["source"] = "skeleton"
    return out
