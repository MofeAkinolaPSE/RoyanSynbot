"""Writes a report about one record from its dossier only, and keeps it (reportGUide.md s12).

Step 4 of the sequence: the person has chosen the type, the record, reviewed what was gathered
and added notes. The writer receives exactly that dossier - no retrieval, no past reports, no
other records - and the dossier is attached as the appendix, so every statement can be checked.

A failed model call raises; it never stores an apology as a report. Clinical summaries are
saved as drafts that only a doctor (or admin) can approve.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

from src.fin.db import ex, q, q1, tx
from src.services import report_subjects as rs

log = logging.getLogger(__name__)

SIGNOFF_ROLES = {"doctor", "admin"}
APPROVER_ROLES = {"management", "admin", "quality_assurance", "finance"}


class ReportError(RuntimeError):
    pass


SYSTEM = """You write formal reports for The Royan Hospital, Lagos, from ONE record that has been gathered for you.

Rules - follow every one:
1. Use only the facts, texts and tables in the record provided. Never add facts, figures, names, dates or causes that are not there.
2. Where the record says "not recorded", or a fact is missing, say plainly that it is not recorded. Do not guess or fill it in.
3. Quote money exactly as given (Naira, ₦). Quote dates as given. Do not recompute totals that are given.
4. Write in plain, professional British English. No filler, no "as an AI", no apologies.
5. Clinical records: report what clinicians recorded. Never offer a diagnosis, prognosis or treatment advice of your own. Mark unverified results as unverified.
6. Output Markdown only: one '## ' heading per section, in exactly the order and with exactly the titles given, each followed by its text. Tables may be used where they help. No title line, no appendix - those are added for you."""


def _llm(system: str, user: str) -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise ReportError("The report writer is not configured (DEEPSEEK_API_KEY is not set)")
    try:
        r = requests.post("https://api.deepseek.com/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), "temperature": 0.2,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                          timeout=120)
    except requests.RequestException as exc:
        raise ReportError(f"The report writer could not be reached: {exc}") from exc
    if r.status_code != 200:
        raise ReportError(f"The report writer failed ({r.status_code}). Try again shortly.")
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    if not text.strip():
        raise ReportError("The report writer returned nothing. Try again.")
    return text.strip()


def _record_block(d: Dict[str, Any]) -> str:
    lines = [f"RECORD: {d['title']}" + (f" ({d['subtitle']})" if d.get("subtitle") else ""), "", "FACTS:"]
    lines += [f"- {f['label']}: {f['value']}" for f in d["facts"]]
    for t in d["texts"]:
        lines += ["", f"{t['label'].upper()}:", t["value"]]
    for t in d["tables"]:
        lines += ["", f"TABLE - {t['title']} (columns: {' | '.join(t['columns'])}):"]
        lines += [" | ".join(str(c) for c in r) for r in t["rows"][:60]]
    if d["gaps"]:
        lines += ["", "NOT RECORDED IN THE SYSTEM:"] + [f"- {g}" for g in d["gaps"]]
    return "\n".join(lines)


def _split_sections(text: str, sections: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", text)
    found = {parts[i].strip().lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    out = []
    for i, s in enumerate(sections, 1):
        out.append({"section_id": s["id"], "title": s["title"], "order": i,
                    "content": found.get(s["title"].lower(), "_This section was not written - regenerate the report._")})
    return out


def generate(user: Dict[str, Any], report_type: str, kind: str, id_: str, notes: Optional[str] = None) -> Dict[str, Any]:
    roles = user.get("roles") or []
    d = rs.dossier(roles, report_type, kind, id_)
    if (notes or "").strip():
        d["texts"].append({"label": "Notes from the person requesting the report", "value": notes.strip()})
    t = rs.TYPE_BY_KEY[report_type]
    sections = rs.sections_for(report_type, kind)
    title = d["title"] if kind in ("period", "current") else f"{t['name']}: {d['title']}"
    prompt = (f"Write the {t['name']} titled \"{title}\".\n\nSections, in this order:\n"
              + "\n".join(f"{i}. {s['title']} - {s['hint']}" for i, s in enumerate(sections, 1))
              + "\n\n" + _record_block(d))
    body = _llm(SYSTEM, prompt)
    secs = _split_sections(body, sections)
    appendix = rs.dossier_markdown(d)
    needs = bool(t.get("needs_signoff"))
    head = f"# {title}\n\n" + ("> **Draft - not valid until approved by the responsible clinician.**\n\n" if needs else "")
    full = head + "\n\n".join(f"## {s['title']}\n\n{s['content']}" for s in secs) + "\n\n" + appendix
    with tx() as conn:
        r = q1(conn, """INSERT INTO royan_record_reports (report_type, subject_kind, subject_id, subject_label, title, full_report,
                                                         sections, facts, author_notes, status, needs_signoff, created_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s) RETURNING id::text AS id, created_at""",
               (report_type, kind, str(id_), d["title"], title, full, json.dumps(secs, default=str), json.dumps(d, default=str),
                (notes or "").strip() or None, "draft" if needs else "complete", needs, str(user.get("sub"))))
    from src.db import audit_event
    audit_event("record_report_written", {"type": report_type, "kind": kind, "id": str(id_)}, actor_id=str(user.get("sub")),
                subject_type=kind, subject_id=str(id_))
    return get(user, r["id"])


def _visible(user: Dict[str, Any], row: Dict[str, Any]) -> bool:
    return row["subject_kind"] in rs.kinds_for(user.get("roles") or [])


def library(user: Dict[str, Any], kind: Optional[str] = None, subject_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    kinds = rs.kinds_for(user.get("roles") or [])
    if not kinds:
        return []
    with tx() as conn:
        rows = q(conn, """SELECT r.id::text AS id, r.report_type, r.subject_kind, r.subject_id, r.subject_label, r.title, r.status,
                                 r.needs_signoff, r.created_at, r.approved_at, COALESCE(s.full_name, u.email) AS created_by_name,
                                 COALESCE(s2.full_name, u2.email) AS approved_by_name
                          FROM royan_record_reports r
                          LEFT JOIN royan_users u ON u.id::text=r.created_by LEFT JOIN royan_staff s ON s.user_id=u.id
                          LEFT JOIN royan_users u2 ON u2.id::text=r.approved_by LEFT JOIN royan_staff s2 ON s2.user_id=u2.id
                          WHERE r.subject_kind = ANY(%s) AND (%s::text IS NULL OR r.subject_kind=%s)
                            AND (%s::text IS NULL OR r.subject_id=%s)
                          ORDER BY r.created_at DESC LIMIT %s""", (kinds, kind, kind, subject_id, subject_id, limit))
    for r in rows:
        r["type_name"] = rs.TYPE_BY_KEY.get(r["report_type"], {}).get("name", r["report_type"])
    return rows


def get(user: Dict[str, Any], rid: str) -> Dict[str, Any]:
    with tx() as conn:
        r = q1(conn, """SELECT id::text AS id, report_type, subject_kind, subject_id, subject_label, title, full_report, sections,
                               author_notes, status, needs_signoff, created_by, created_at, approved_by, approved_at
                        FROM royan_record_reports WHERE id::text=%s""", (rid,))
    if not r or not _visible(user, r):
        raise LookupError("Report not found")
    r["type_name"] = rs.TYPE_BY_KEY.get(r["report_type"], {}).get("name", r["report_type"])
    return r


def approve(user: Dict[str, Any], rid: str) -> Dict[str, Any]:
    r = get(user, rid)
    roles = {str(x).lower() for x in user.get("roles") or []}
    if r["needs_signoff"]:
        if not roles & SIGNOFF_ROLES:
            raise PermissionError("A clinical summary is approved by the responsible clinician (doctor)")
    elif not (roles & APPROVER_ROLES or str(user.get("sub")) == r["created_by"]):
        raise PermissionError("Only the author or a manager can approve this report")
    if r["status"] == "approved":
        return r
    full = r["full_report"].replace("> **Draft - not valid until approved by the responsible clinician.**\n\n", "")
    with tx() as conn:
        ex(conn, """UPDATE royan_record_reports SET status='approved', approved_by=%s, approved_at=now(), full_report=%s, updated_at=now()
                    WHERE id::text=%s""", (str(user.get("sub")), full, rid))
    from src.db import audit_event
    audit_event("record_report_approved", {"id": rid, "type": r["report_type"]}, actor_id=str(user.get("sub")),
                subject_type="record_report", subject_id=rid)
    return get(user, rid)
