"""FINAL comprehensive extraction pass (2026-08-22).

Goal stated by the user: "complete all extractions even the lower value
data ... so we don't have to come back to it." This is the last dump scan
-- it stages every remaining Hope table that holds real Royan
operational/clinical/reference data, so no future work needs to re-read
the 685MB dump.

Deliberately EXCLUDED (documented, not overlooked):
  * Standard vendor vocabulary shipped with the EHR, not Royan's own data:
    hl7_* (~20 tables), phvs_* (~14), loinc_*, snomed_*, ucums,
    observation_*/specimen_*/result_status_* code tables. These are
    licensed reference code systems with no Royan content and no target
    table in synbot_health.
  * CakePHP framework plumbing: acos, aros, aros_acos, session_permissions,
    package_permissions, linked_modules, configurations, widgets,
    user_dashboard_charts, error_service_logs, inboxes, outboxes,
    cqmlists, cqmreports.
  * Generic geo lookups: cities, states, countries, districts, zips.
  * Confirmed-empty tables (205 of the 506) -- nothing to extract.
  * `audits` (271K) / `patient_audits`: CakePHP row-change audit trail.
    Real, but it is framework-level change history for a system being
    retired; synbot_health has its own audit_logs (migration 112). Left
    out deliberately -- extracting it would add 271K rows with no consumer.

NOTE: radiology_test_orders is included here specifically to close the
known coverage gap -- only 24,080 of ~58,065 real Hope radiology orders
were ever loaded (~41%), a pre-existing gap flagged earlier in this
project with no traceable load script.

Usage: python scripts/extract_final_sweep.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.mysql_dump import parse_dump
from staging.sqlite_store import StagingStore

DUMP_PATH = str(
    Path(__file__).resolve().parent.parent / "Docs" / "NEw Dump" / "db_drmnigeria-20260125.sql.gz"
)

TARGET_TABLES = {
    # --- Known coverage gap: radiology orders (only 41% ever loaded) ---
    "radiology_test_orders", "radiologies",
    # --- Nursing flowsheet decode chain (review_patient_details is staged;
    #     these are needed to decode its serialized `values` blob) ---
    "review_categories", "review_sub_categories", "review_sub_categories_options",
    "review_category_customizations", "review_date_time_slots",
    # --- Pharmacy / inventory reference + activity ---
    "products", "product_rates", "inventory_suppliers", "store_locations",
    "manufacturer_companies", "medical_items", "inventory_trackings",
    "stock_maintenances", "stock_maintenance_details", "store_requisition_particulars",
    "medical_requisitions", "medical_requisition_details",
    "suggested_drugs", "elderly_medications", "new_crop_allergies",
    "treatment_medications", "treatment_medication_details", "vaccine_drugs",
    "ndc_masters",
    # --- Orders / clinical activity ---
    "patient_orders", "order_data_masters", "order_sentences",
    "ambulatory_result_outboxes", "hl7_messages",
    # --- Lab reference ---
    "test_groups", "specimen_types", "micro_organisms", "multiple_lab_masters",
    "laboratory_aoe_codes",
    # --- Accounting / finance ---
    "accounts", "accounting_groups", "voucher_logs", "voucher_references",
    "companies", "vat_classes", "credit_types", "advance_types",
    "insurance_authorizations",
    # --- Theatre / procedures / surgery ---
    "surgeries", "surgery_categories", "surgery_subcategories",
    "procedure_masters", "procedure_histories", "procedure_performs",
    "preferencecards", "preferencecard_instrumentitems", "preferencecard_oritems",
    "preferencecard_procedures", "preferencecard_spditems",
    # --- Patient history / context ---
    "screenings", "immunizations", "patient_past_histories",
    "patient_personal_histories", "past_medical_records", "past_medical_histories",
    "family_histories", "patient_smokings", "patient_ivfs",
    "patient_blood_transfusion_form", "patient_document_types",
    # --- Infection control / quality ---
    "nosocomial_infections", "nosocomial_infection_parents", "infection_counts",
    "ssi_records", "surgical_site_infections", "uti_records", "vap_records",
    "bsi_records", "air_sampling_reports", "fumigations", "fumigation_reports",
    "interventions", "incidents", "incident_types", "intrinsic_risk_factors",
    "ventilator_check_lists", "ventilator_nurse_check_lists", "tracheostomy_consents",
    # --- Staffing / scheduling / org reference ---
    "chambers", "physician_speciality_codes", "speciality_cats",
    "refferer_doctors", "service_providers", "marketing_teams",
    "designations", "initials", "name_types", "licensure_types",
    "visit_types", "service_categories", "service_sub_categories",
    "schedule_blocks", "time_slots", "roles",
    "opt_appointments", "opt_appointment_details",
    "send_referrals", "sign_symptoms",
}

ENTITY_MAP = {t: f"hope_{t}" for t in TARGET_TABLES}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for {len(TARGET_TABLES)} tables")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"final_sweep_{int(time.time())}"

    empty = []
    for hope_table, entity in sorted(ENTITY_MAP.items()):
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        if count:
            print(f"  {hope_table:38s} -> {count:>8,} rows staged")
        else:
            empty.append(hope_table)

    print(f"\nEmpty (0 rows, nothing to load): {len(empty)}")
    print("  " + ", ".join(empty))
    print("Done.")


if __name__ == "__main__":
    main()
