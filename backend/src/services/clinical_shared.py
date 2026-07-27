"""Small, dependency-light helpers shared across clinical routers.

Kept separate from clinical_service.py (which uses raw psycopg2 cursors for
encounter-level documentation) because this module deliberately uses the
db.table() query builder instead, matching how canonical.py, nursing.py, and
pharmacy_dispensing.py already query patient data.
"""
from __future__ import annotations

from typing import List, Dict, Any

from src.db import db
from src.constants import TABLE_ALLERGIES


def get_patient_allergies(patient_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    """Return a patient's allergy rows.

    Previously duplicated ad hoc in canonical.py (no status filter, so
    resolved/inactive allergies leaked into the CPRS snapshot) and in
    pharmacy_dispensing.py (filtered on a nonexistent `active` column, so the
    dispense-time interaction check silently matched nothing). This is the
    one place that query should live.
    """
    query = db.table(TABLE_ALLERGIES).select("id,allergen,reaction,severity,status").eq("patient_id", patient_id)
    if active_only:
        query = query.eq("status", "active")
    result = query.execute()
    return result.data or []
