"""Extract Royan's real HMO/payer list and patient<->HMO links from Hope.

Hope has no table literally named "hmo" -- the real payer master list is
`tariff_standards` (staged as hope_tariff_standards), confirmed by content
inspection: real Nigerian HMO/insurer names (MANSARD, IHMS, GNI. GREAT
NIGERIA INSURANCE, REDCARE, ...), completely distinct from the vendor
demo data found in `insurance_companies` (Nagpur, India addresses, all
is_deleted=1) and the pre-existing royan_hmos seed rows (US Medicare/
Medicaid-style names, all created at one identical timestamp) -- neither
of which is used here.

The patient<->HMO link is three hops, not direct:
  corporate_patient_details.corporate_bill_id
    -> corporate_super_bills.id
    -> corporate_super_bills.tariff_standard_id
    -> tariff_standards.name

corporate_patient_details.billing_id (which would link straight to a
specific royan_billing row) is populated on only 1 of 815 rows -- too
sparse to build a reliable billing-row backfill on, so this only tags the
*patient* (royan_patients.hmo_provider + patient_type), not individual
historical bills. Hope itself didn't consistently record that link; going
forward, new bills should default hmo_id from the patient's own record
rather than trying to reconstruct history that was never captured.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_str

# Row id=1 in tariff_standards is a CSV-header-as-data artifact (every field
# equals its own column name, e.g. name="name") -- not a real payer.
_ARTIFACT_NAMES = {"name"}


def transform_hmos(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_names: set = set()
    for row in sorted(raw_rows, key=lambda r: int(r.get("id") or 0)):
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id or name.strip().lower() in _ARTIFACT_NAMES:
            continue
        key = name.strip().lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        out.append({
            "name":              name.strip(),
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def transform_patient_links(
    corporate_patient_details: List[Dict[str, Any]],
    corporate_super_bills: List[Dict[str, Any]],
    tariff_standards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # tariff_standard_id -> real HMO name (same filtering as transform_hmos,
    # so a link never resolves to a deleted/artifact payer)
    tariff_name_by_id: Dict[str, str] = {}
    for row in tariff_standards:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id or name.strip().lower() in _ARTIFACT_NAMES:
            continue
        tariff_name_by_id[ext_id] = name.strip()

    # super_bill id -> tariff_standard_id
    tariff_id_by_super_bill: Dict[str, str] = {}
    for row in corporate_super_bills:
        sb_id = safe_str(row.get("id"))
        tariff_id = safe_str(row.get("tariff_standard_id"))
        if sb_id and tariff_id:
            tariff_id_by_super_bill[sb_id] = tariff_id

    out = []
    for row in corporate_patient_details:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        hope_patient_id = safe_str(row.get("patient_id"))
        super_bill_id = safe_str(row.get("corporate_bill_id"))
        if not hope_patient_id or not super_bill_id:
            continue

        tariff_id = tariff_id_by_super_bill.get(super_bill_id)
        hmo_name = tariff_name_by_id.get(tariff_id) if tariff_id else None
        if not hmo_name:
            continue

        out.append({
            "_hope_patient_id": hope_patient_id,
            "hmo_name":         hmo_name,
        })
    return out
