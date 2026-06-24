"""MySQL dump file parser and schema discoverer.

Streams a mysqldump .sql (or gzip-compressed .sql.gz) file line-by-line so
memory usage is bounded to the size of one SQL statement rather than the full
file.  A 2.7 GB dump is processed without loading it all into RAM.

Key differences from the original:
  - No fh.read() — line-by-line iteration via open() or gzip.open()
  - .gz files are decompressed on-the-fly; no temp file needed
  - target_tables filter: skips INSERT parsing for unneeded tables (big speedup
    on 500+ table dumps when you only need 10-15 entities)
  - Multi-line INSERT fallback: buffers until ';' when an INSERT spans lines

Public API:
    parse_dump(filepath, target_tables=None) -> {table: [row_dict, ...]}
    discover(filepath) -> None  (prints schema report, zero writes)
"""
from __future__ import annotations

import gzip
import re
from typing import Dict, List, Optional, Set


# ─── Public API ──────────────────────────────────────────────────────────────

def discover(filepath: str) -> None:
    """Print every table and column found in the dump. Safe — zero writes."""
    print(f"\n{'='*60}")
    print(f"DISCOVERY REPORT: {filepath}")
    print(f"{'='*60}\n")

    # sample_size=1: only collect one row per table — no point loading millions of rows
    # just to see column names
    data = parse_dump(filepath, sample_size=1)

    print(f"Found {len(data)} tables:\n")
    for table_name in sorted(data.keys()):
        rows = data[table_name]
        cols = list(rows[0].keys()) if rows else []
        print(f"  TABLE: {table_name}  ({len(rows)} rows)")
        if cols:
            for col in cols:
                sample = rows[0].get(col)
                sample_str = (
                    f"  e.g. {repr(str(sample)[:60])}"
                    if sample is not None
                    else "  (null in first row)"
                )
                print(f"    - {col}{sample_str}")
        else:
            print("    (no rows / could not extract columns)")
        print()

    print(f"{'='*60}")
    print("Paste this output to Claude to update field_maps.py.\n")


def parse_dump(
    filepath: str,
    target_tables: Optional[Set[str]] = None,
    sample_size: Optional[int] = None,
) -> Dict[str, List[dict]]:
    """Stream-parse a mysqldump .sql or .sql.gz file.

    Reads line-by-line so peak memory is bounded to one INSERT statement
    (~1–100 MB for large tables) rather than the full file.

    target_tables: when provided, INSERT rows are collected only for these
                   table names.  All tables still appear as schema entries.
                   Example: target_tables={'patients', 'diagnoses', 'service_bills'}

    sample_size:   when provided, stop collecting rows for a table once this
                   many rows have been collected.  Use sample_size=1 for fast
                   schema discovery on multi-GB files.
    """
    open_fn = gzip.open if filepath.endswith(".gz") else open

    schema: Dict[str, List[str]] = {}
    data: Dict[str, List[dict]] = {}

    # CREATE TABLE accumulation (multi-line, but small)
    _in_create = False
    _cur_table: Optional[str] = None
    _create_lines: List[str] = []

    # Multi-line INSERT fallback buffer
    _pending_table: Optional[str] = None
    _pending_cols: List[str] = []
    _pending_buf: List[str] = []
    _pending_skip = False

    _CREATE_START = re.compile(
        r"CREATE\s+TABLE\s+[`\"]?(\w+)[`\"]?\s*\(", re.IGNORECASE
    )
    _INSERT_HDR = re.compile(
        r"INSERT\s+INTO\s+[`\"]?(\w+)[`\"]?\s*"
        r"(?:\(([^)]+)\)\s*)?VALUES\s*",
        re.IGNORECASE,
    )

    with open_fn(filepath, "rt", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\r\n")
            stripped = line.lstrip()

            # ── Pending multi-line INSERT ─────────────────────────────────
            if _pending_table is not None:
                if not _pending_skip:
                    _pending_buf.append(line)

                # Check for end of this INSERT statement
                if _line_closes_stmt(line):
                    if not _pending_skip:
                        full = "\n".join(_pending_buf)
                        # Find VALUES start in buffered content
                        vm = re.search(r"VALUES\s*", full, re.IGNORECASE)
                        if vm:
                            vblock = full[vm.end():].rstrip(";").rstrip()
                            rows = _parse_values_block(vblock, _pending_cols)
                            data[_pending_table].extend(rows)
                    _pending_table = None
                    _pending_cols = []
                    _pending_buf = []
                    _pending_skip = False
                continue

            # ── Inside a CREATE TABLE block ───────────────────────────────
            if _in_create:
                _create_lines.append(line)
                # End when a line's visible content begins with ')'
                if stripped.startswith(")"):
                    cols = _parse_column_names("\n".join(_create_lines))
                    if cols:
                        schema[_cur_table] = cols
                    data.setdefault(_cur_table, [])
                    _in_create = False
                    _cur_table = None
                    _create_lines = []
                continue

            # ── CREATE TABLE start ────────────────────────────────────────
            m = _CREATE_START.match(stripped)
            if m:
                _cur_table = m.group(1).lower()
                _in_create = True
                _create_lines = [line]
                continue

            # ── INSERT INTO ───────────────────────────────────────────────
            m = _INSERT_HDR.search(line)
            if not m:
                continue

            table = m.group(1).lower()
            ecols_str = m.group(2)
            cols: List[str] = (
                [c.strip().strip("`\"").lower() for c in ecols_str.split(",")]
                if ecols_str
                else schema.get(table, [])
            )

            data.setdefault(table, [])

            # Skip if: not in target_tables, or sample_size already reached
            skip = (
                (target_tables is not None and table not in target_tables)
                or (sample_size is not None and len(data[table]) >= sample_size)
            )

            # Typical mysqldump: entire VALUES block is on this same line
            values_tail = line[m.end():]
            if _line_closes_stmt(values_tail):
                if not skip:
                    vblock = values_tail.rstrip().rstrip(";")
                    rows = _parse_values_block(vblock, cols)
                    data[table].extend(rows)
            else:
                # Multi-line INSERT — buffer until ';'
                _pending_table = table
                _pending_cols = cols
                _pending_skip = skip
                _pending_buf = [line] if not skip else []

    return data


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _line_closes_stmt(line: str) -> bool:
    """Return True if *line* contains a semicolon that terminates a statement
    (i.e. the ';' is not inside a quoted string)."""
    in_q = False
    i = 0
    s = line
    while i < len(s):
        c = s[i]
        if c == "\\" and in_q:
            i += 2
            continue
        if c == "'":
            if in_q and i + 1 < len(s) and s[i + 1] == "'":
                i += 2
                continue
            in_q = not in_q
        elif c == ";" and not in_q:
            return True
        i += 1
    return False


def _parse_column_names(table_body: str) -> List[str]:
    """Extract column names from the body of a CREATE TABLE statement."""
    cols: List[str] = []
    for line in table_body.splitlines():
        line = line.strip().rstrip(",")
        if re.match(
            r"(PRIMARY|UNIQUE|KEY|INDEX|CONSTRAINT|FULLTEXT|CHECK)\b",
            line, re.IGNORECASE,
        ):
            continue
        m = re.match(r"[`\"](\w+)[`\"]", line)
        if m:
            cols.append(m.group(1).lower())
    return cols


# ─── Row value parsing (unchanged logic, same correctness) ───────────────────

def _parse_values_block(block: str, cols: List[str]) -> List[dict]:
    """Extract all (v1, v2, ...) tuples from a SQL VALUES block."""
    rows: List[dict] = []
    i = 0
    s = block

    while i < len(s):
        if s[i] != "(":
            i += 1
            continue

        j, depth, in_q = i + 1, 1, False
        while j < len(s) and depth > 0:
            c = s[j]
            if c == "\\" and in_q:
                j += 2
                continue
            if c == "'":
                if in_q and j + 1 < len(s) and s[j + 1] == "'":
                    j += 2
                    continue
                in_q = not in_q
            elif not in_q:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            j += 1

        row_content = s[i + 1: j - 1]
        values = _split_values(row_content)

        if values:
            if cols:
                row: dict = {}
                for k, v in zip(cols, values):
                    row[k] = v
                for k in cols[len(values):]:
                    row[k] = None
                rows.append(row)
            else:
                rows.append({str(idx): v for idx, v in enumerate(values)})

        i = j

    return rows


def _split_values(row_str: str) -> List[Optional[str]]:
    """Split a comma-separated SQL row string, respecting quoted strings."""
    values: List[Optional[str]] = []
    current: List[str] = []
    in_q = False
    i = 0

    while i < len(row_str):
        c = row_str[i]
        if c == "\\" and in_q:
            current.append(c)
            if i + 1 < len(row_str):
                current.append(row_str[i + 1])
            i += 2
            continue
        if c == "'":
            if in_q and i + 1 < len(row_str) and row_str[i + 1] == "'":
                current.append("'")
                i += 2
                continue
            in_q = not in_q
            current.append(c)
        elif c == "," and not in_q:
            values.append(_cook_value("".join(current).strip()))
            current = []
        else:
            current.append(c)
        i += 1

    if current or not values:
        values.append(_cook_value("".join(current).strip()))

    return values


def _cook_value(raw: str) -> Optional[str]:
    """Convert a raw SQL token to Python str or None."""
    if raw.upper() == "NULL" or raw == "":
        return None
    if raw.startswith("'") and raw.endswith("'"):
        inner = raw[1:-1]
        inner = inner.replace("\\'", "'").replace("''", "'")
        return inner
    return raw
