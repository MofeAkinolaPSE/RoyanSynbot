r"""Standalone, offline-safe inventory scanner for the DRM Hope network share.

Why this exists: the client VPN that exposes the Hope data folders (e.g. Z:\)
doesn't let this machine reach the internet at the same time — so Claude Code
itself becomes unreachable while the share is mounted. This script needs
nothing but the Python standard library plus this repo's own
extractors/mysql_dump.py, so it keeps working the whole time the VPN is up.
Run it, let it finish (or interrupt it — it's resumable), then hand the
report files in scan_reports/ back to Claude once you're off the VPN.

It is READ-ONLY: it never writes to Z:\, never touches the live Postgres DB,
never calls out to Docker or the network. It only reads files under the given
root and writes a local report.

What it does:
  1. Walks the whole tree (files + folders), no matter how it's organized.
  2. For anything that looks like a MySQL dump (.sql, .sql.gz, or content-
     sniffed even with a mangled/truncated extension like "db_drmnigeria.sq"
     or "DGXYEX~N.SQL") — files over --stage-threshold-mb (default 20MB) are
     first copied to local disk in resumable chunks (retries on network
     drops, logs progress every ~15s, resumes an interrupted copy from
     wherever it left off rather than restarting) — parsing a slow/flaky
     network share directly can stall for an hour on one file with zero
     feedback and no way to resume; a local copy doesn't have that problem.
     Then it runs a cheap schema-only pass (1 sample row per table) to get
     every table name + its columns, using the exact same streaming parser
     the real ETL pipeline uses (parse_dump), so a 650MB+ gz file is handled
     in bounded memory.
  3. For any table whose name matches one of our missing entities (payments,
     insurance_claims, dispensing, lab_results — see KEYWORD_MAP below) or
     that TABLE_HINTS doesn't already know about, it re-parses just that
     table (target_tables filter) to get an exact row count.
  4. For folders that aren't SQL dumps (raw MySQL data directories full of
     .frm/.ibd/.MYD files, phpMyAdmin per-table export folders, or just
     unknown junk) it classifies what kind of folder it is and lists what's
     in it, without trying to parse binary files.
  5. Writes everything to data-assimilation/scan_reports/<name>/:
       - inventory.jsonl   one line per scanned item — safe to tail/resume from
       - keyword_matches.json   candidate tables for each missing entity
       - SUMMARY.md        human-readable report, read this first
       - scan.log          full progress/error log

Usage (from the data-assimilation/ directory, or anywhere — path is absolute):
    python scripts/scan_hope_source.py Z:\\
    python scripts/scan_hope_source.py Z:\\ --fresh          # ignore prior progress, rescan everything
    python scripts/scan_hope_source.py Z:\\ --max-parse-mb 4096   # raise the per-file parse size cap
    python scripts/scan_hope_source.py Z:\\ --stage-threshold-mb 5   # stage smaller files too
    python scripts/scan_hope_source.py Z:\\ --no-stage        # parse directly, skip local staging

If the VPN drops mid-scan, just re-run the exact same command:
  - Fully-scanned files are skipped (matched by path + size + mtime).
  - A file that was only partly staged (interrupted copy) resumes the copy
    from the byte it stopped at, instead of restarting from zero.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractors.mysql_dump import parse_dump  # noqa: E402

try:
    from transformers.field_maps import TABLE_HINTS  # noqa: E402
except Exception:
    TABLE_HINTS = {}

# ─── Config ───────────────────────────────────────────────────────────────────

SQL_EXTENSIONS = {".sql", ".gz"}
MYSQL_DATADIR_EXTENSIONS = {".frm", ".ibd", ".myd", ".myi", ".ibz", ".mysql"}
DEFAULT_MAX_PARSE_MB = 2048  # files bigger than this are sized/logged, not parsed
DIR_LISTING_CAP = 300        # max entries reported per "unknown folder" listing
MAX_WALK_DEPTH = 8           # safety bound on recursive directory walk

DEFAULT_STAGE_THRESHOLD_MB = 20   # files bigger than this get copied local before parsing
COPY_CHUNK_BYTES = 8 * 1024 * 1024
COPY_MAX_RETRIES = 8
COPY_RETRY_BACKOFF_SECONDS = 5
COPY_PROGRESS_INTERVAL_SECONDS = 15

# Substrings (lowercased) that flag a table as a candidate for one of the
# entities that came back with zero rows in the last ingestion audit. These
# are guesses based on Hope's known naming style (service_bills, diagnosis_drugs,
# insurance_companies, etc.) — anything that matches gets an exact row count;
# anything that *doesn't* match any keyword AND isn't already in TABLE_HINTS
# still shows up in the "uncategorized tables" section so nothing is silently
# dropped just because our guesses were wrong.
KEYWORD_MAP: dict[str, list[str]] = {
    "payments":         ["payment", "receipt", "cash_transaction", "collection", "remittance",
                          "cash_receipt", "revenue"],
    "insurance_claims":  ["claim", "hmo_claim", "insurance_claim", "reimbursement", "preauth"],
    "dispensing":        ["dispens", "drug_issue", "medication_issue", "stock_issue", "drug_out",
                          "pharmacy_issue"],
    "lab_results":       ["lab_result", "test_result", "investigation_result", "lab_report",
                          "result"],
}

KNOWN_TABLE_NAMES: set[str] = {t.lower() for hints in TABLE_HINTS.values() for t in hints}


# ─── Small helpers ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class Logger:
    """Writes to stdout AND a log file, flushing every line — so a killed
    process (VPN drop, closed terminal) still leaves a readable trail."""

    def __init__(self, path: Path):
        self.fh = open(path, "a", encoding="utf-8")

    def log(self, msg: str) -> None:
        line = f"[{_now()}] {msg}"
        print(line)
        self.fh.write(line + "\n")
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def sniff_is_sql(path: Path, peek_bytes: int = 8192) -> bool:
    """Content-sniff a file with an unfamiliar extension (e.g. 'db_drmnigeria.sq',
    'DGXYEX~N.SQL', 'nig.sql') to see if it's actually a SQL dump."""
    try:
        if path.suffix.lower() == ".gz":
            return True  # handled by parse_dump's gzip.open path regardless of pre-extension
        with open(path, "rb") as fh:
            chunk = fh.read(peek_bytes)
        text = chunk.decode("utf-8", errors="ignore").upper()
        return ("CREATE TABLE" in text) or ("INSERT INTO" in text) or ("-- MYSQL DUMP" in text)
    except Exception:
        return False


def match_keywords(table_name: str) -> list[str]:
    name = table_name.lower()
    return [entity for entity, kws in KEYWORD_MAP.items() if any(kw in name for kw in kws)]


def stage_locally(src: Path, dest: Path, log: Logger) -> Path:
    """Copy *src* (likely on a slow/flaky network share) to local *dest* before
    parsing, in resumable chunks with retry-on-drop and periodic progress logs.

    Streaming a gzip parse directly off a slow SMB-over-VPN handle can stall
    for over an hour on a single file with zero feedback and no way to resume
    a drop. A plain chunked sequential copy tolerates that link far better —
    and if dest already exists at a smaller size than src (a copy that was
    interrupted last time), this resumes from that byte offset instead of
    starting over.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_size = src.stat().st_size

    if dest.exists() and dest.stat().st_size == src_size:
        log.log(f"    (already staged locally, skipping copy: {dest})")
        return dest

    resume_offset = dest.stat().st_size if dest.exists() else 0
    if resume_offset > src_size:
        log.log(f"    (staged copy is larger than source — discarding and restarting: {dest})")
        resume_offset = 0

    mode = "ab" if resume_offset else "wb"
    log.log(f"    staging locally -> {dest} "
             f"({'resuming from ' + str(round(resume_offset / 1e6)) + ' MB' if resume_offset else 'starting'}, "
             f"{src_size / 1e6:.1f} MB total)")

    attempt = 0
    copied = resume_offset
    t_last_log = time.time()
    t_start = time.time()
    while True:
        try:
            with open(src, "rb") as fsrc, open(dest, mode) as fdst:
                if resume_offset:
                    fsrc.seek(resume_offset)
                while True:
                    chunk = fsrc.read(COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    copied += len(chunk)
                    now = time.time()
                    if now - t_last_log >= COPY_PROGRESS_INTERVAL_SECONDS:
                        pct = 100 * copied / src_size if src_size else 100
                        mb_per_s = (copied - resume_offset) / max(now - t_start, 0.001) / 1e6
                        log.log(f"      ... {copied / 1e6:.0f} / {src_size / 1e6:.0f} MB "
                                f"({pct:.0f}%, ~{mb_per_s:.2f} MB/s)")
                        t_last_log = now
            break  # completed without error
        except OSError as exc:
            attempt += 1
            if attempt > COPY_MAX_RETRIES:
                raise
            log.log(f"    !! copy interrupted ({exc}) — retry {attempt}/{COPY_MAX_RETRIES} "
                     f"in {COPY_RETRY_BACKOFF_SECONDS}s, resuming from {copied / 1e6:.0f} MB")
            time.sleep(COPY_RETRY_BACKOFF_SECONDS)
            resume_offset = dest.stat().st_size if dest.exists() else 0
            copied = resume_offset
            mode = "ab" if resume_offset else "wb"

    log.log(f"    staged {copied / 1e6:.0f} MB in {time.time() - t_start:.0f}s")
    return dest


def classify_datadir_or_export(files: list[str]) -> Optional[str]:
    exts = [Path(f).suffix.lower() for f in files]
    if any(e in MYSQL_DATADIR_EXTENSIONS for e in exts):
        return "mysql_datadir"
    sql_like = sum(1 for e in exts if e == ".sql")
    if sql_like >= 3 and sql_like >= 0.5 * max(len(files), 1):
        return "per_table_sql_export"
    return None


# ─── Progress / resumability ──────────────────────────────────────────────────

def load_scanned_set(inventory_path: Path) -> set[tuple]:
    """Returns {(relpath, size, mtime_int), ...} for everything already recorded."""
    seen: set[tuple] = set()
    if not inventory_path.exists():
        return seen
    with open(inventory_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seen.add((rec["path"], rec.get("size"), rec.get("mtime")))
            except Exception:
                continue
    return seen


def append_record(inventory_path: Path, record: dict) -> None:
    with open(inventory_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


# ─── Core scan logic ──────────────────────────────────────────────────────────

def scan_sql_file(path: Path, log: Logger, stage_dir: Optional[Path], stage_threshold_bytes: int) -> dict:
    """Schema-only discovery pass + exact row counts for keyword-matched or
    unknown tables. Returns a record dict for inventory.jsonl.

    For files above stage_threshold_bytes, copies to stage_dir first (see
    stage_locally) and parses the local copy instead of streaming the parse
    directly off the (possibly slow/flaky) source path. The record's "path"
    always reflects the true source location, not the staged copy.
    """
    t0 = time.time()
    size = path.stat().st_size
    record: dict[str, Any] = {
        "type": "sql_dump",
        "path": str(path),
        "size": size,
        "mtime": int(path.stat().st_mtime),
        "tables": {},
        "error": None,
    }
    parse_path = path
    try:
        if stage_dir is not None and size > stage_threshold_bytes:
            staged = stage_dir / path.name
            parse_path = stage_locally(path, staged, log)
            record["staged_copy"] = str(parse_path)

        schema = parse_dump(str(parse_path), sample_size=1)
        candidate_tables: list[str] = []
        for table, rows in schema.items():
            matches = match_keywords(table)
            known = table in KNOWN_TABLE_NAMES
            sample = rows[0] if rows else {}
            record["tables"][table] = {
                "columns": list(sample.keys()),
                "sample_row": {k: (str(v)[:80] if v is not None else None) for k, v in sample.items()},
                "keyword_matches": matches,
                "already_known": known,
                "row_count": None,
            }
            if matches or not known:
                candidate_tables.append(table)

        # Phase B: exact row counts, but only for tables worth counting —
        # keeps this fast even on 500+ table dumps.
        if candidate_tables:
            log.log(f"    -> re-parsing {len(candidate_tables)} candidate table(s) for exact row counts: {candidate_tables}")
            counted = parse_dump(str(parse_path), target_tables=set(candidate_tables))
            for table in candidate_tables:
                record["tables"][table]["row_count"] = len(counted.get(table, []))
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        log.log(f"    !! ERROR parsing {path}: {record['error']}")

    record["scan_seconds"] = round(time.time() - t0, 1)
    return record


def scan_unknown_file(path: Path) -> dict:
    preview = ""
    try:
        with open(path, "rb") as fh:
            preview = fh.read(500).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return {
        "type": "unknown_file",
        "path": str(path),
        "size": path.stat().st_size,
        "mtime": int(path.stat().st_mtime),
        "preview": preview,
    }


def scan_directory_shallow(path: Path, log: Logger, depth: int, max_depth: int) -> dict:
    """Classify a directory (mysql datadir / per-table sql export / generic)
    without recursively content-scanning every file inside it."""
    try:
        entries = list(os.scandir(path))
    except Exception as exc:
        return {"type": "directory", "path": str(path), "error": f"{type(exc).__name__}: {exc}"}

    files = [e.name for e in entries if e.is_file()]
    subdirs = [e for e in entries if e.is_dir()]
    ext_counts: dict[str, int] = {}
    for f in files:
        ext = Path(f).suffix.lower() or "(none)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    kind = classify_datadir_or_export(files)
    record: dict[str, Any] = {
        "type": kind or "directory",
        "path": str(path),
        "file_count": len(files),
        "subdir_count": len(subdirs),
        "extension_counts": ext_counts,
        "sample_files": files[:DIR_LISTING_CAP],
    }
    if kind == "mysql_datadir":
        table_names = sorted({Path(f).stem for f in files if Path(f).suffix.lower() in MYSQL_DATADIR_EXTENSIONS})
        record["inferred_table_names"] = table_names
        record["keyword_matches"] = {t: match_keywords(t) for t in table_names if match_keywords(t)}
    elif kind == "per_table_sql_export":
        table_names = sorted({Path(f).stem for f in files if Path(f).suffix.lower() == ".sql"})
        record["inferred_table_names"] = table_names
        record["keyword_matches"] = {t: match_keywords(t) for t in table_names if match_keywords(t)}

    log.log(f"  DIR {path}  ({len(files)} files, {len(subdirs)} subdirs) -> {record['type']}")
    return record


def walk_and_scan(
    root: Path, report_dir: Path, log: Logger, fresh: bool, max_parse_mb: int,
    stage_dir: Optional[Path], stage_threshold_mb: int,
) -> None:
    inventory_path = report_dir / "inventory.jsonl"
    scanned = set() if fresh else load_scanned_set(inventory_path)
    max_parse_bytes = max_parse_mb * 1024 * 1024
    stage_threshold_bytes = stage_threshold_mb * 1024 * 1024

    def visit(current: Path, depth: int) -> None:
        if depth > MAX_WALK_DEPTH:
            log.log(f"  (max depth reached, not descending further into {current})")
            return
        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name.lower())
        except Exception as exc:
            log.log(f"  !! cannot list {current}: {exc}")
            return

        # First classify this directory itself as a whole (datadir/export/generic)
        files_here = [e.name for e in entries if e.is_file()]
        kind = classify_datadir_or_export(files_here) if files_here else None
        if kind in ("mysql_datadir", "per_table_sql_export"):
            key = (str(current), None, None)
            if key not in scanned:
                rec = scan_directory_shallow(current, log, depth, MAX_WALK_DEPTH)
                append_record(inventory_path, rec)
                scanned.add(key)
            return  # don't also descend file-by-file into a classified datadir/export folder

        # Otherwise: record this dir's shallow listing once, then recurse into subdirs,
        # and individually scan any SQL-looking files directly inside it.
        key = (str(current), None, None)
        if key not in scanned:
            rec = scan_directory_shallow(current, log, depth, MAX_WALK_DEPTH)
            append_record(inventory_path, rec)
            scanned.add(key)

        for entry in entries:
            p = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                visit(p, depth + 1)
                continue

            try:
                size = entry.stat().st_size
                mtime = int(entry.stat().st_mtime)
            except Exception as exc:
                log.log(f"  !! cannot stat {p}: {exc}")
                continue

            rel_key = (str(p), size, mtime)
            if rel_key in scanned:
                continue

            ext = p.suffix.lower()
            looks_sql = ext in SQL_EXTENSIONS or sniff_is_sql(p)
            if looks_sql:
                if size > max_parse_bytes:
                    log.log(f"  SKIP (too large: {size / 1e6:.0f}MB > cap) {p}")
                    append_record(inventory_path, {
                        "type": "sql_dump_oversize", "path": str(p), "size": size, "mtime": mtime,
                    })
                else:
                    log.log(f"  SQL  {p}  ({size / 1e6:.1f} MB)")
                    rec = scan_sql_file(p, log, stage_dir, stage_threshold_bytes)
                    append_record(inventory_path, rec)
            else:
                append_record(inventory_path, scan_unknown_file(p))
            scanned.add(rel_key)

    log.log(f"Starting scan of {root} (fresh={fresh}, max_parse_mb={max_parse_mb})")
    visit(root, 0)
    log.log("Scan complete.")


# ─── Report generation ────────────────────────────────────────────────────────

def build_reports(report_dir: Path) -> None:
    inventory_path = report_dir / "inventory.jsonl"
    records = []
    with open(inventory_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    keyword_hits: dict[str, list[dict]] = {k: [] for k in KEYWORD_MAP}
    uncategorized: list[dict] = []
    errors: list[dict] = []
    unknown_files: list[dict] = []
    dump_files = 0
    total_tables = 0

    for rec in records:
        if rec.get("type") == "sql_dump":
            dump_files += 1
            if rec.get("error"):
                errors.append(rec)
            for table, info in rec.get("tables", {}).items():
                total_tables += 1
                for entity in info.get("keyword_matches", []):
                    keyword_hits[entity].append({
                        "file": rec["path"], "table": table,
                        "row_count": info.get("row_count"),
                        "columns": info.get("columns"),
                    })
                if not info.get("keyword_matches") and not info.get("already_known"):
                    uncategorized.append({"file": rec["path"], "table": table, "row_count": info.get("row_count")})
        elif rec.get("type") in ("mysql_datadir", "per_table_sql_export"):
            for table, matches in rec.get("keyword_matches", {}).items():
                for entity in matches:
                    keyword_hits[entity].append({
                        "file": rec["path"], "table": table, "row_count": None, "columns": None,
                    })
        elif rec.get("type") == "unknown_file":
            unknown_files.append(rec)
        elif rec.get("error"):
            errors.append(rec)

    with open(report_dir / "keyword_matches.json", "w", encoding="utf-8") as fh:
        json.dump(keyword_hits, fh, indent=2, default=str)

    lines = []
    lines.append(f"# Hope Source Scan Summary — {_now()}\n")
    lines.append(f"Scanned {len(records)} items ({dump_files} SQL dumps, {total_tables} tables total found).\n")

    lines.append("## Candidate tables for missing entities\n")
    for entity, hits in keyword_hits.items():
        lines.append(f"### {entity}")
        if not hits:
            lines.append("_No candidate tables found by keyword — see 'uncategorized tables' below, "
                          "the real table name may not match our guessed keywords._\n")
            continue
        for h in hits:
            rc = h["row_count"] if h["row_count"] is not None else "?"
            lines.append(f"- `{h['table']}` in `{h['file']}` — {rc} rows"
                          + (f" — columns: {', '.join(h['columns'])}" if h.get("columns") else ""))
        lines.append("")

    if uncategorized:
        lines.append("## Uncategorized tables (not matched to any known entity or keyword)\n")
        lines.append("_Review these — the missing entity's real table name might be here under a name "
                      "we didn't think to guess._\n")
        for u in sorted(uncategorized, key=lambda x: -(x["row_count"] or 0))[:200]:
            lines.append(f"- `{u['table']}` in `{u['file']}` — {u['row_count']} rows")
        lines.append("")

    if unknown_files:
        lines.append("## Unknown / non-SQL files encountered (worth a manual look)\n")
        for u in unknown_files[:100]:
            lines.append(f"- `{u['path']}` ({u['size']} bytes) — preview: `{u['preview'][:120]!r}`")
        lines.append("")

    if errors:
        lines.append("## Errors while scanning\n")
        for e in errors:
            lines.append(f"- `{e['path']}`: {e.get('error')}")
        lines.append("")

    with open(report_dir / "SUMMARY.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help=r"Root path to scan, e.g. Z:\ or Z:\some\subfolder")
    parser.add_argument("--fresh", action="store_true", help="Ignore prior progress and rescan everything")
    parser.add_argument("--max-parse-mb", type=int, default=DEFAULT_MAX_PARSE_MB,
                         help=f"Skip full-parsing SQL files bigger than this (default {DEFAULT_MAX_PARSE_MB}MB)")
    parser.add_argument("--report-dir", default=None,
                         help="Where to write the report (default: data-assimilation/scan_reports/<root-name>)")
    parser.add_argument("--stage-threshold-mb", type=int, default=DEFAULT_STAGE_THRESHOLD_MB,
                         help=f"Copy files bigger than this to local disk before parsing (default "
                              f"{DEFAULT_STAGE_THRESHOLD_MB}MB) — much more resilient than parsing "
                              f"straight off a slow/flaky network share. 0 disables staging.")
    parser.add_argument("--no-stage", action="store_true",
                         help="Disable local staging entirely; parse directly from the source path")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: root path does not exist or is not reachable right now: {root}")
        print("(If this is a VPN-only network share, make sure the VPN is connected.)")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent / "scan_reports"
    report_dir = Path(args.report_dir) if args.report_dir else base / (root.name or root.drive.replace(":", "") or "scan")
    report_dir.mkdir(parents=True, exist_ok=True)

    stage_dir = None if args.no_stage else report_dir / "_staged"

    log = Logger(report_dir / "scan.log")
    try:
        walk_and_scan(
            root, report_dir, log, fresh=args.fresh, max_parse_mb=args.max_parse_mb,
            stage_dir=stage_dir, stage_threshold_mb=args.stage_threshold_mb,
        )
        log.log("Building SUMMARY.md and keyword_matches.json ...")
        build_reports(report_dir)
        log.log(f"Done. Read {report_dir / 'SUMMARY.md'} first.")
    except KeyboardInterrupt:
        log.log("Interrupted by user — progress is saved in inventory.jsonl, re-run the same command to resume.")
        build_reports(report_dir)
    except Exception:
        log.log("FATAL ERROR:\n" + traceback.format_exc())
        build_reports(report_dir)
        raise
    finally:
        log.close()


if __name__ == "__main__":
    main()
