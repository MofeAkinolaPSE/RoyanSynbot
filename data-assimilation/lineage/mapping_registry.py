"""Data Lineage Engine — Mapping Registry.

The single queryable view of "where did every Hope column go?": reads the
de facto source of truth (transformers/field_maps.py's *_MAP dicts — the
exact mappings the ETL actually executed) and joins it against the columns
observed in the raw Hope dump (staging/hope_staging.db) to classify every
source column as Mapped / Ignored, and every mapping as Used / Unmatched.

Static by design: the Hope ingestion was a one-time dump (2026-06-10), so
this is a documentation/audit artifact, not a live scanner.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, Dict, List

sys.path.insert(0, ".")
from transformers import field_maps  # noqa: E402

# Hope raw staging table → the *_MAP dict the ETL applied to it
ENTITY_MAPS: Dict[str, dict] = {
    "raw_patients":     field_maps.PATIENT_MAP,
    "raw_appointments": field_maps.APPOINTMENT_MAP,
    "raw_admissions":   field_maps.ADMISSION_MAP,
    "raw_lab":          field_maps.LAB_MAP,
    "raw_pharmacy":     field_maps.PHARMACY_MAP,
    "raw_billing":      field_maps.BILLING_MAP,
}

# Sentinel destinations in field_maps that aren't real Synbot columns
_SENTINELS = {"__patient_lookup__"}


def get_source_columns(staging_db_path: str, table: str, sample_size: int = 200) -> List[str]:
    """Union of JSON keys across a sample of raw rows — the observed Hope schema."""
    con = sqlite3.connect(staging_db_path)
    try:
        cur = con.cursor()
        cur.execute(f'SELECT data FROM "{table}" LIMIT {int(sample_size)}')
        keys: set = set()
        for (payload,) in cur.fetchall():
            try:
                keys.update(json.loads(payload).keys())
            except Exception:
                continue
        return sorted(keys)
    finally:
        con.close()


def build_registry(staging_db_path: str) -> List[Dict[str, Any]]:
    """One row per (entity, hope_column): its Synbot destination and status.

    Status values:
      mapped    — Hope column observed in the dump AND covered by the field map
      ignored   — observed in the dump but NOT in the field map (data left behind)
      unmatched — in the field map but never observed in the dump (dead mapping)
    """
    registry: List[Dict[str, Any]] = []
    for table, fmap in ENTITY_MAPS.items():
        observed = set(get_source_columns(staging_db_path, table))
        mapped_sources = {k.lower() for k in fmap.keys()}

        for col in sorted(observed):
            dest = fmap.get(col) or fmap.get(col.lower())
            if dest and dest not in _SENTINELS:
                status = "mapped"
            elif dest in _SENTINELS:
                status, dest = "mapped", "(patient FK resolution)"
            else:
                status, dest = "ignored", None
            registry.append({
                "entity": table,
                "hope_column": col,
                "synbot_destination": dest,
                "status": status,
            })

        for src, dest in fmap.items():
            if src.lower() not in {c.lower() for c in observed}:
                registry.append({
                    "entity": table,
                    "hope_column": src,
                    "synbot_destination": dest if dest not in _SENTINELS else "(patient FK resolution)",
                    "status": "unmatched",
                })
    return registry
