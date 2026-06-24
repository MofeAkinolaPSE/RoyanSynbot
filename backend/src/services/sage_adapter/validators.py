"""
Sage adapter validators stub — Placeware/pharma import pipeline removed.

Provides header-resolution helpers and the REQUIRED_* / ALIASES_* constants
so that existing callers in app.py compile without the original Sage CSV
validator infrastructure. All functions accept arbitrary input and return
safe empty results; the import pipeline endpoints are dead code paths.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Required-column lists (empty — no Sage datasets expected in hospital DB)
# ---------------------------------------------------------------------------

REQUIRED_CUSTOMERS:   List[str] = []
REQUIRED_AR:          List[str] = []
REQUIRED_AP:          List[str] = []
REQUIRED_GL:          List[str] = []
REQUIRED_INVENTORY:   List[str] = []
REQUIRED_STAFF:       List[str] = []


# ---------------------------------------------------------------------------
# Alias maps (empty — no column aliasing needed)
# ---------------------------------------------------------------------------

ALIASES_CUSTOMERS:    Dict[str, List[str]] = {}
ALIASES_AR:           Dict[str, List[str]] = {}
ALIASES_AP:           Dict[str, List[str]] = {}
ALIASES_GL:           Dict[str, List[str]] = {}
ALIASES_INVENTORY:    Dict[str, List[str]] = {}
ALIASES_STAFF:        Dict[str, List[str]] = {}
ALIASES_HR_PAYROLL:   Dict[str, List[str]] = {}
ALIASES_HR_ABSENCES:  Dict[str, List[str]] = {}
ALIASES_OPS_ORDERS:   Dict[str, List[str]] = {}
ALIASES_OPS_DOWNTIME: Dict[str, List[str]] = {}
ALIASES_CRM_PIPELINE: Dict[str, List[str]] = {}


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

def resolve_headers(
    headers: List[str],
    required: List[str],
    aliases: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, str], List[str], List[str], List[str]]:
    """Return (header_map, missing, unknown, duplicates).

    Stub: passes all provided headers through unchanged; no required columns
    so missing is always empty.
    """
    header_map = {h: h for h in headers}
    missing:    List[str] = []
    unknown:    List[str] = []
    duplicates: List[str] = []
    return header_map, missing, unknown, duplicates


def canonicalize_rows(
    rows: List[Dict[str, Any]],
    header_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return rows with keys renamed according to header_map.

    Stub: returns rows unchanged (header_map is identity mapping).
    """
    return [{header_map.get(k, k): v for k, v in row.items()} for row in rows]
