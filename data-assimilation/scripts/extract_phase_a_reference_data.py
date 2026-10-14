"""Combined extraction for the "Data-First, Then UI" plan (post-deployment
meeting-minutes follow-up, 2026-08-20/21): order sets, SOAP/exam templates,
diagnosis catalog, allergies, radiology results, referrals, consent forms,
structured discharge, and nurse notes/observations -- one dump pass covering
every Phase A stream, since parse_dump()'s cost is dominated by total bytes
scanned, not table count.

Usage: python scripts/extract_phase_a_reference_data.py
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
    # Order sets
    "orderset_masters", "orderset_category_mappings", "order_subcategories", "order_categories",
    # SOAP / exam templates
    "note_templates", "note_template_texts", "doctor_templates", "doctor_template_texts",
    "templates", "template_categories", "template_sub_categories", "template_type_contents",
    # Diagnosis catalog
    "diagnoses", "diagnosis_masters",
    # Allergies
    "allergy_masters", "drug_allergies", "patient_allergies", "env_allergies",
    # Radiology results
    "radiology_results", "radiology_reports", "radiology_2d_echo_result",
    "radiology_doctor_notes", "radiology_manual_entry",
    # Referrals
    "patient_referrals", "referral_to_hospitals", "referral_to_specialists", "referring_providers",
    # Consent
    "consent_forms", "consents", "surgery_consent_forms", "anaesthesia_consent_forms",
    "dama_consent_forms", "hippa_consents",
    # Structured discharge
    "discharge_summaries", "discharge_details", "discharge_drugs", "dischargeby_consultants",
    # Nurse notes / observations
    "nurse_notes", "observation_charts",
}

ENTITY_MAP = {
    "orderset_masters":              "hope_orderset_masters",
    "orderset_category_mappings":    "hope_orderset_category_mappings",
    "order_subcategories":           "hope_order_subcategories",
    "order_categories":              "hope_order_categories",
    "note_templates":                "hope_note_templates",
    "note_template_texts":           "hope_note_template_texts",
    "doctor_templates":              "hope_doctor_templates",
    "doctor_template_texts":         "hope_doctor_template_texts",
    "templates":                     "hope_templates",
    "template_categories":           "hope_template_categories",
    "template_sub_categories":       "hope_template_sub_categories",
    "template_type_contents":        "hope_template_type_contents",
    "diagnoses":                     "hope_diagnoses",
    "diagnosis_masters":             "hope_diagnosis_masters",
    "allergy_masters":               "hope_allergy_masters",
    "drug_allergies":                "hope_drug_allergies",
    "patient_allergies":             "hope_patient_allergies",
    "env_allergies":                 "hope_env_allergies",
    "radiology_results":             "hope_radiology_results",
    "radiology_reports":             "hope_radiology_reports",
    "radiology_2d_echo_result":      "hope_radiology_2d_echo_result",
    "radiology_doctor_notes":        "hope_radiology_doctor_notes",
    "radiology_manual_entry":        "hope_radiology_manual_entry",
    "patient_referrals":             "hope_patient_referrals",
    "referral_to_hospitals":         "hope_referral_to_hospitals",
    "referral_to_specialists":       "hope_referral_to_specialists",
    "referring_providers":           "hope_referring_providers",
    "consent_forms":                 "hope_consent_forms",
    "consents":                      "hope_consents",
    "surgery_consent_forms":         "hope_surgery_consent_forms",
    "anaesthesia_consent_forms":     "hope_anaesthesia_consent_forms",
    "dama_consent_forms":            "hope_dama_consent_forms",
    "hippa_consents":                "hope_hippa_consents",
    "discharge_summaries":           "hope_discharge_summaries",
    "discharge_details":             "hope_discharge_details",
    "discharge_drugs":               "hope_discharge_drugs",
    "dischargeby_consultants":       "hope_dischargeby_consultants",
    "nurse_notes":                   "hope_nurse_notes",
    "observation_charts":            "hope_observation_charts",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for {len(TARGET_TABLES)} tables")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"phase_a_reference_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
