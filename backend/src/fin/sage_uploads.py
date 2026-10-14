"""Sage exports uploaded by Finance from Roy Books (Setup > Sage imports).

Royan's finance team is still bringing 2025 and 2026 up to date in Sage. As each
set is ready they upload the reports here instead of handing files to IT:

  1. upload  - the workbooks are saved and each one is recognised by its content
               (any file name). Reports not uploaded are taken from the last set
               that loaded, so a partial upload is fine; the screen says which.
  2. check   - a full dry run of src.fin.sage_import: the history is rebuilt and
               tied to the uploaded trial balance and balance sheet, then rolled
               back. Nothing changes.
  3. load    - the same run, kept. Only a set that ties can be loaded. The files
               become the "last set" for the next upload.

Files live under FIN_DATA_DIR (the backend's data volume): sage/uploads/<id>/ and
sage/current/ (one workbook per report).
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from src.fin import audit, sage_import
from src.fin.db import jsonb, q, q1
from src.fin.errors import FinError, not_found

MAX_FILE = 60 * 1024 * 1024


def root() -> str:
    base = os.getenv("FIN_DATA_DIR") or "/app/data/fin"
    try:
        os.makedirs(os.path.join(base, "sage", "current"), exist_ok=True)
        return base
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "roy-books")
        os.makedirs(os.path.join(fallback, "sage", "current"), exist_ok=True)
        return fallback


def current_dir() -> str:
    return os.path.join(root(), "sage", "current")


def upload_dir(upload_id: str) -> str:
    return os.path.join(root(), "sage", "uploads", str(upload_id))


def _describe_cached(path: str) -> Dict[str, Any]:
    """Reading a 190k-line General Ledger takes seconds; remember each file's summary until it changes."""
    import json
    st = os.stat(path)
    key = f"{os.path.basename(path)}|{st.st_size}|{int(st.st_mtime)}"
    cache_file = os.path.join(root(), "sage", "describe-cache.json")
    try:
        cache = json.load(open(cache_file, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if key not in cache:
        kind = sage_import.classify(path)
        cache[key] = {**sage_import.describe(kind, sage_import.rows_of(path)), "file": os.path.basename(path)} if kind else None
        try:
            json.dump(cache, open(cache_file, "w", encoding="utf-8"))
        except OSError:
            pass
    return cache[key]


def current_set() -> Dict[str, Any]:
    """What the next upload falls back to: report -> file, rows and dates."""
    files = sage_import.resolve([current_dir()])
    return {k: _describe_cached(p) for k, p in files.items()}


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\- ]", "_", os.path.basename(name or "upload.xlsx"))[:120] or "upload.xlsx"


def create(conn, ctx, files: List[Tuple[str, bytes]], note: Optional[str] = None) -> Dict[str, Any]:
    ctx.require("migration.stage")
    if not files:
        raise FinError("VALIDATION_FAILED", "Choose the Sage report files (.xlsx) to upload")
    row = q1(conn, """INSERT INTO fin_sage_uploads (legal_entity_id, note, created_by) VALUES (%s,%s,%s) RETURNING id""",
             (ctx.entity_id, note, ctx.actor_id))
    d = upload_dir(str(row["id"]))
    os.makedirs(d, exist_ok=True)
    found: Dict[str, Any] = {}
    unknown: List[str] = []
    for name, raw in files:
        if len(raw) > MAX_FILE:
            raise FinError("VALIDATION_FAILED", f"{name} is larger than {MAX_FILE // (1024 * 1024)} MB")
        if not name.lower().endswith((".xlsx", ".xlsm")):
            unknown.append(f"{name} (not an Excel workbook - export from Sage as Excel)")
            continue
        p = os.path.join(d, _safe(name))
        with open(p, "wb") as fh:
            fh.write(raw)
        try:
            kind = sage_import.classify(p)
        except Exception:
            kind = None
        if not kind:
            unknown.append(f"{name} (not a Sage report Roy Books reads)")
            os.remove(p)
            continue
        if kind in found:
            unknown.append(f"{name} (a second {sage_import.TITLES[kind]} - the first one is used)")
            os.remove(p)
            continue
        found[kind] = {**sage_import.describe(kind, sage_import.rows_of(p)), "file": name}
    ex_files = {"uploaded": found, "unrecognised": unknown}
    q1(conn, "UPDATE fin_sage_uploads SET files=%s WHERE id=%s RETURNING id", (jsonb(ex_files), row["id"]))
    audit.record(conn, ctx, "SAGE_UPLOAD_RECEIVED", "sage_upload", row["id"],
                 metadata={"reports": sorted(found), "unrecognised": len(unknown)})
    return get(conn, ctx.entity_id, str(row["id"]))


def get(conn, entity_id: str, upload_id: str) -> Dict[str, Any]:
    u = q1(conn, "SELECT * FROM fin_sage_uploads WHERE id=%s AND legal_entity_id=%s", (upload_id, entity_id))
    if not u:
        raise not_found("Sage upload", upload_id)
    uploaded = (u["files"] or {}).get("uploaded", {})
    last = current_set()
    plan = []
    for k, title in sage_import.TITLES.items():
        if k in uploaded:
            plan.append({"kind": k, "title": title, "source": "uploaded", **uploaded[k]})
        elif k in last:
            plan.append({"kind": k, "title": title, "source": "last set", **last[k]})
        else:
            plan.append({"kind": k, "title": title, "source": "missing", "required": k in sage_import.REQUIRED})
    gl_to = next((p.get("to") for p in plan if p["kind"] == "gl"), None)
    stale = [p["title"] for p in plan if p["source"] == "last set" and gl_to and p.get("to") and p["to"] < gl_to[:7]
             and p["kind"] in ("invoices", "crj")]
    return {**u, "plan": plan, "missing_required": [p["title"] for p in plan if p["source"] == "missing" and p.get("required")],
            "warnings": [f"{t} comes from the last set and stops before the new General Ledger - upload the new one too" for t in stale]}


def list_uploads(conn, entity_id: str) -> Dict[str, Any]:
    rows = q(conn, """SELECT id, status, note, files, created_by, created_at, checked_at, loaded_by, loaded_at,
                             check_result->'tie_out'->>'ties' AS ties, COALESCE(load_result, check_result)->>'as_of' AS as_of
                      FROM fin_sage_uploads WHERE legal_entity_id=%s ORDER BY created_at DESC LIMIT 50""", (entity_id,))
    loaded = q1(conn, "SELECT as_of, loaded_at FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key='import-log'", (entity_id,))
    return {"uploads": rows, "history_as_of": loaded["as_of"] if loaded else None,
            "history_loaded_at": loaded["loaded_at"] if loaded else None, "current_set": current_set()}


def _dirs(upload_id: str) -> List[str]:
    return [upload_dir(upload_id), current_dir()]


def check(conn_factory, ctx_entity: str, upload_id: str, actor: str) -> Dict[str, Any]:
    """Dry run. `conn_factory` is the caller's tx(); the import opens its own transaction."""
    with conn_factory() as conn:
        u = get(conn, ctx_entity, upload_id)
        if u["status"] == "LOADED":
            raise FinError("INVALID_STATE_TRANSITION", "This upload is already loaded")
        if u["missing_required"]:
            raise FinError("VALIDATION_FAILED", "Missing Sage reports: " + ", ".join(u["missing_required"]))
    try:
        res = sage_import.run(_dirs(upload_id), dry_run=True, actor=actor)
        status = "CHECKED"
    except FinError as e:
        res = {"error": e.to_detail()}
        status = "FAILED"
    with conn_factory() as conn:
        q1(conn, """UPDATE fin_sage_uploads SET status=%s, check_result=%s, checked_at=now() WHERE id=%s RETURNING id""",
           (status, jsonb(res), upload_id))
        return get(conn, ctx_entity, upload_id)


def load(conn_factory, ctx_entity: str, upload_id: str, actor: str) -> Dict[str, Any]:
    with conn_factory() as conn:
        u = get(conn, ctx_entity, upload_id)
        if u["status"] != "CHECKED" or not ((u["check_result"] or {}).get("tie_out") or {}).get("ties"):
            raise FinError("INVALID_STATE_TRANSITION",
                           "Run the check first; only a set whose history ties to its trial balance and balance sheet can load")
    files = sage_import.resolve(_dirs(upload_id))
    res = sage_import.run(files, actor=actor)
    # The loaded set becomes the fallback for the next upload, one workbook per report.
    cur = current_dir()
    previous = sage_import.resolve([cur])
    for kind, path in files.items():
        if os.path.dirname(path) == cur:
            continue
        if kind in previous:
            os.remove(previous[kind])
        shutil.copy2(path, os.path.join(cur, os.path.basename(path)))
    with conn_factory() as conn:
        q1(conn, """UPDATE fin_sage_uploads SET status='LOADED', load_result=%s, loaded_by=%s, loaded_at=now()
                    WHERE id=%s RETURNING id""", (jsonb(res), actor, upload_id))
        return get(conn, ctx_entity, upload_id)


def discard(conn, ctx, upload_id: str) -> Dict[str, Any]:
    ctx.require("migration.stage")
    u = get(conn, ctx.entity_id, upload_id)
    if u["status"] == "LOADED":
        raise FinError("INVALID_STATE_TRANSITION", "A loaded upload is the record of what was loaded and cannot be discarded")
    shutil.rmtree(upload_dir(upload_id), ignore_errors=True)
    q1(conn, "DELETE FROM fin_sage_uploads WHERE id=%s RETURNING id", (upload_id,))
    return {"discarded": upload_id, "at": dt.datetime.now().isoformat()}
