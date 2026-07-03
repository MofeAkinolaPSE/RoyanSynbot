"""Enrichment transformer helpers — Chapter 6 / Blueprint Phase 7.

Pure functions that build in-memory lookup maps from the PostgreSQL master
tables and normalize free-text name strings for fuzzy matching.

These are used by loaders/enrichment_loader.py to resolve text columns
to FK integer IDs without touching the staging SQLite layer.

All functions in this module are stateless and dependency-free (no psycopg2).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

# ─────────────────────────────────────────────────────────────────────────────
# Name normalisation
# ─────────────────────────────────────────────────────────────────────────────

# Titles/honorifics to strip before matching
_TITLES: Set[str] = {
    "dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
    "nurse", "pharm", "lab", "rev", "pastor", "engr", "chief", "barr",
}

_EXTRA_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALPHA_RE = re.compile(r"[^a-z0-9 ]")


def normalize_name(raw: Optional[str]) -> Optional[str]:
    """Lowercase, strip titles, collapse whitespace. Returns None if blank."""
    if not raw:
        return None
    text = raw.strip().lower()
    text = _NON_ALPHA_RE.sub(" ", text)
    parts = _EXTRA_WHITESPACE_RE.split(text)
    parts = [p for p in parts if p and p not in _TITLES]
    result = " ".join(parts).strip()
    return result or None


def name_variants(first: Optional[str], last: Optional[str]) -> List[str]:
    """Return candidate normalized name strings for a staff row.

    Generates: 'first last', 'last first', single tokens — so that
    free-text entries like 'Adeyemi Sarah' match 'Sarah Adeyemi'.
    """
    f = normalize_name(first) or ""
    l = normalize_name(last) or ""
    variants: List[str] = []
    if f and l:
        variants.append(f"{f} {l}")
        variants.append(f"{l} {f}")
    if f:
        variants.append(f)
    if l:
        variants.append(l)
    return [v for v in variants if v]


# ─────────────────────────────────────────────────────────────────────────────
# Lookup map builders  (DB cursor passed in — no psycopg2 import needed here)
# ─────────────────────────────────────────────────────────────────────────────

def build_staff_lookup(rows: List[Dict]) -> Dict[str, int]:
    """Build {normalized_name_variant: staff_id} from royan_staff rows.

    Accepts a list of dicts with keys: id, first_name, last_name, staff_code.
    Multiple variants are generated per staff member so that Hope free-text
    like 'Dr Jane Doe', 'Doe Jane', or just 'Jane' all resolve correctly.
    """
    lookup: Dict[str, int] = {}
    for row in rows:
        sid = row.get("id")
        if not sid:
            continue
        for v in name_variants(row.get("first_name"), row.get("last_name")):
            # First entry wins — if two doctors share a single-name variant,
            # the full 'first last' match from a different encounter overrides.
            if v not in lookup:
                lookup[v] = int(sid)
        # Also index by staff_code (e.g. 'CON001') in case Hope stored that
        code = str(row.get("staff_code") or "").strip().lower()
        if code and code not in lookup:
            lookup[code] = int(sid)
    return lookup


def resolve_staff_id(
    raw_name: Optional[str],
    lookup: Dict[str, int],
) -> Optional[int]:
    """Resolve a free-text doctor/staff name to a royan_staff.id.

    Returns None if no match found or if raw_name looks like a bare integer
    (Hope sometimes stores staff_id numbers in consultant_sb column).
    """
    if not raw_name:
        return None
    # Bare integer = Hope internal staff ID, not a name — skip
    if str(raw_name).strip().isdigit():
        return None
    key = normalize_name(raw_name)
    if not key:
        return None
    return lookup.get(key)


def build_dept_lookup(rows: List[Dict]) -> Dict[str, int]:
    """Build {code_lower: dept_id, name_lower: dept_id} from royan_departments rows."""
    lookup: Dict[str, int] = {}
    for row in rows:
        did = row.get("id")
        if not did:
            continue
        code = str(row.get("code") or "").strip().lower()
        name = str(row.get("name") or "").strip().lower()
        if code:
            lookup[code] = int(did)
        if name and name not in lookup:
            lookup[name] = int(did)
    return lookup


def resolve_dept_id(
    raw_dept: Optional[str],
    lookup: Dict[str, int],
) -> Optional[int]:
    """Resolve encounter.department text to royan_departments.id."""
    if not raw_dept:
        return None
    key = raw_dept.strip().lower()
    return lookup.get(key)


def build_hmo_lookup(rows: List[Dict]) -> Dict[str, int]:
    """Build {lower(hmo_name): hmo_id} from royan_hmos rows."""
    lookup: Dict[str, int] = {}
    for row in rows:
        hid = row.get("id")
        if not hid:
            continue
        name = str(row.get("name") or "").strip().lower()
        if name:
            lookup[name] = int(hid)
    return lookup


def resolve_hmo_id(
    raw_name: Optional[str],
    lookup: Dict[str, int],
) -> Optional[int]:
    if not raw_name:
        return None
    return lookup.get(raw_name.strip().lower())


def build_lab_catalog_lookup(rows: List[Dict]) -> Dict[str, int]:
    """Build {code_lower: catalog_id} from royan_lab_catalog rows."""
    lookup: Dict[str, int] = {}
    for row in rows:
        cid = row.get("id")
        code = str(row.get("code") or "").strip().lower()
        if cid and code:
            lookup[code] = int(cid)
    return lookup


def build_formulary_lookup(rows: List[Dict]) -> Dict[str, int]:
    """Build {code_lower: formulary_id, lower(generic_name): formulary_id}."""
    lookup: Dict[str, int] = {}
    for row in rows:
        fid = row.get("id")
        if not fid:
            continue
        code = str(row.get("code") or "").strip().lower()
        name = str(row.get("generic_name") or "").strip().lower()
        if code:
            lookup[code] = int(fid)
        if name and name not in lookup:
            lookup[name] = int(fid)
    return lookup
