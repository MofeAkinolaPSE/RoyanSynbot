"""Extract real discharge events from Hope's `discharge_details` table
(staged as hope_discharge_details) -> royan_discharge_records.

Of the four structured-discharge tables in Hope, only discharge_details has
real data (9,448 rows) -- discharge_summaries/discharge_drugs/
dischargeby_consultants are all confirmed empty. discharge_details itself
is thin: ward/bed/timing only, no clinical narrative (no condition,
diagnosis, medications, or follow-up instructions in the source at all).
discharge_condition is left unset here (not fabricated as "stable") so
Postgres's own column default applies rather than this pipeline asserting
a specific clinical fact Hope never actually recorded.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        hope_pid = safe_str(row.get("patient_id"))
        ext_id = safe_str(row.get("id"))
        discharged_at = safe_date(row.get("discharge_starts_on")) or safe_date(row.get("create_time"))
        if not hope_pid or not ext_id or not discharged_at:
            continue

        out.append({
            "_hope_patient_id":  hope_pid,
            "_discharge_at":     discharged_at,
            "discharged_at":     discharged_at,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
