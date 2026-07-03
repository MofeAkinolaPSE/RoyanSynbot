# RoyanHealth — Data Quality Audit Report
**Date:** 2026-06-26  
**Total records audited:** 1,293,645 across 6 core clinical tables  
**Purpose:** Phase 3 pipeline assessment — identify what is production-ready vs. what requires enrichment before clinical use

---

## Executive Summary

| Area | Status | Verdict |
|------|--------|---------|
| Referential integrity (FK chains) | All green — 0 broken FKs | Production-ready |
| Duplicate patients | 102 same-name/DOB combos, 0 duplicate MRNs | Acceptable |
| Lab test names | 100% are placeholder — completely unreadable | Critical gap |
| Encounter clinical fields | 0% consulting doctor, triage, ward, discharge | Critical gap |
| Prescription data | 100% complete on all fields | Production-ready |
| Billing structure | 33,575 bills with ₦0 subtotal; 0% payment method | Needs enrichment |
| Appointments | Missing reason + encounter link on all imported rows | Partial gap |
| Master data tables | Wards, beds, HMOs, staff catalog — all empty | Blocking gap |

---

## 1. Duplicate Patients

| Check | Result |
|-------|--------|
| Total patients | 60,935 |
| Duplicate MRNs (same MRN, multiple rows) | **0** — clean |
| Same name + DOB (potential person duplicates) | **102 combos** |
| Duplicate external_id values | **0** — clean |

**Interpretation:** No hard duplicates in the database. The 102 same name+DOB matches are likely real people who share a name and date of birth (common in Nigerian datasets — twins, family members). They have different MRNs, so the system treats them as distinct patients. No action required unless manual review flags a specific pair.

---

## 2. Orphaned Records (FK Integrity)

| Relationship | Broken FKs | Result |
|---|---|---|
| Encounters → Patients | 0 | ✓ Clean |
| Lab Orders → Patients | 0 | ✓ Clean |
| Lab Orders → Encounters | 0 | ✓ Clean |
| Prescriptions → Patients | 0 | ✓ Clean |
| Prescriptions → Encounters | 0 | ✓ Clean |
| Billing → Patients | 0 | ✓ Clean |
| Billing → Encounters | 0 | ✓ Clean |
| Appointments → Patients | 0 | ✓ Clean |
| Appointments → Slots | 0 | ✓ Clean |
| Encounters → Wards | 0 | ✓ (ward_id always NULL — target table empty) |
| Encounters → Beds | 0 | ✓ (bed_id always NULL — target table empty) |

**Verdict:** Referential integrity is perfect across all 11 FK paths. The 1.28M imported records form a fully linked graph. No orphaned clinical records.

---

## 3. Prescriptions with No Encounter

| Check | Count |
|---|---|
| Prescriptions with NULL encounter_id | **0** |
| Prescriptions with orphaned encounter_id | **0** |
| Prescriptions with orphaned patient_id | **0** |

**Verdict:** 258,635 prescriptions are all fully linked. This dataset is production-ready.

---

## 4. Lab Orders — Placeholder Test Names

| Check | Count | % |
|---|---|---|
| Total lab orders | 203,538 | — |
| Placeholder "Imported lab order" | **203,521** | **100.0%** |
| Real test names found | 17 | 0.0% |
| Blank/NULL test_name | 0 | — |

**Only real test name found:** `Full Blood Count` — 17 records (the 68 PESE validation records).

**Root cause:** Hope's `laboratory_test_orders` table does not have a column that matches any of the 8 Hope field names the pipeline tries (`test_name`, `test_type`, `test`, `investigation`, `lab_test`, `description`, `service_name`, `item_name`). The transformer falls back to the placeholder string. The actual column in Hope's DB needs to be discovered via direct schema inspection (`DESCRIBE laboratory_test_orders` in Hope MySQL).

**Impact:** The entire lab module is non-functional from a clinical standpoint. No lab order in the system has an identifiable test name. This is the single highest-priority fix.

**Also noted:** `test_code` is 100% populated (203,520/203,538) — Hope's `laboratory_id` FK to the lab catalog is coming through. If we can join that ID to Hope's `laboratory` master table, we can backfill real test names without re-ingesting.

---

## 5. Unique Master Data Extractable

### Doctors

| Source | Unique Doctors |
|---|---|
| Encounters (consulting_doctor) | **1** — only "Dr. PESE Test" (17 records) |
| Prescriptions (prescribed_by) | **2** |
| Lab orders (ordered_by) | **172** |
| Appointment slots (doctor_name) | **116** |

**Finding:** The `consulting_doctor` field on 518,489 encounters is almost entirely blank — only 17 PESE test records have a doctor name. However, **172 unique doctor names** exist in `royan_lab_orders.ordered_by` and **116 in appointment slots**. These can be extracted to seed `royan_staff` for doctors.

### Departments

| Department | Encounters |
|---|---|
| OPD | 256,471 |
| Laboratory & Diagnostics | 170,514 |
| Pharmacy | 64,257 |
| Billing & Finance | 27,245 |
| Surgery | 2 |

**Finding:** Only 5 distinct departments exist in the data — likely because Hope's department field maps to high-level categories, not specific units (e.g. no "Cardiology", "Obstetrics", "Paediatrics" separation). These 5 can be seeded into a department master table.

### Wards (Inpatient)

Only **1 ward name** appears in encounters with `encounter_type='inpatient'`: **Surgery**. All other inpatients have `department=NULL` for ward context. The `royan_wards` table is empty (0 records).

### Payment Methods (Billing)

`payment_method` is **0% populated** across all 259,081 billing records. Hope does not export payment method — this field will only fill through live billing workflows.

### Services

`royan_service_catalog` has **5 records** (manually seeded, likely test data). No service catalog was imported from Hope.

---

## 6. Critical Field Completeness

### Patients (60,935 records)

| Field | Fill Rate | Status |
|---|---|---|
| mrn | 100.0% | Ready |
| first_name | 100.0% | Ready |
| last_name | 100.0% | Ready |
| date_of_birth | 99.0% | Ready (590 blank) |
| gender | 100.0% | Ready |
| phone | 1.1% (645) | Gap — not in Hope |
| email | 3.9% (2,385) | Gap — rarely in Hope |
| address | 0.0% | Gap — not in Hope |
| next_of_kin_name | 0.0% (8 records) | Gap — not in Hope |
| blood_group | 0.0% (8 records) | Gap — not in Hope |
| genotype | 0.0% | Gap — not in Hope |
| hmo_provider | 0.0% | Gap — not in Hope |
| hmo_id | 0.0% | Gap — not in Hope |

**Verdict:** Identity fields (name, MRN, DOB, gender) are complete. Clinical enrichment fields (blood group, HMO, address, NOK) are empty because Hope does not store them at the level RoyanHealth expects. These must be collected through the patient portal or front-desk registration flow.

---

### Encounters (518,489 records)

| Field | Fill Rate | Status |
|---|---|---|
| patient_id | 100.0% | Ready |
| encounter_type | 100.0% | Ready |
| department | 100.0% | Ready |
| consulting_doctor | 0.0% (17 records) | Critical gap |
| triage_level | 0.0% (18 records) | Critical gap |
| ward_id | 0.0% | Critical gap — wards table empty |
| bed_id | 0.0% | Critical gap — beds table empty |
| chief_complaint | 40.4% (209,379) | Partial |
| diagnosis_notes | 0.0% (17 records) | Critical gap |
| discharge_at | 0.0% (17 records) | Critical gap |

**Finding:** Encounters are structurally complete (all linked to patients, typed, and departmentalized) but clinically empty. The system knows a patient visited, but not who saw them, what was wrong, or what was decided. This reflects Hope's data model — Hope stores clinical detail in diagnosis sub-tables, not in a flat encounter row.

**Root cause of consulting_doctor=0%:** Hope's `diagnoses` table has a `consultant_sb` field (staff ID FK), not a plain text doctor name. The transformer maps it to `consulting_doctor` as a text lookup — but only resolves if the staff name is in the Hope staff table. Since staff data wasn't imported, 518,472 records have no doctor name.

---

### Lab Orders (203,538 records)

| Field | Fill Rate | Status |
|---|---|---|
| patient_id | 100.0% | Ready |
| encounter_id | 100.0% | Ready |
| test_name | 100.0% (but all placeholder) | False positive |
| test_code | 100.0% | Ready — has Hope's lab catalog ID |
| urgency | 100.0% | Ready (defaults to "routine") |
| ordered_by | 100.0% | Ready |
| ordered_at | 100.0% | Ready |
| sample_type | 15.8% (32,072) | Gap |
| sample_collected_at | 0.0% | Gap — not in Hope |

---

### Prescriptions (258,635 records)

| Field | Fill Rate | Status |
|---|---|---|
| patient_id | 100.0% | Ready |
| encounter_id | 100.0% | Ready |
| drug_name | 100.0% | Ready |
| dosage | 100.0% | Ready (may be "as directed" default) |
| frequency | 100.0% | Ready (may be "as directed" default) |
| route | 100.0% | Ready (may be "oral" default) |
| prescribed_by | 100.0% | Ready |
| prescribed_at | 100.0% | Ready |

**Verdict:** Best-quality imported dataset. All fields populated. Prescriptions are production-ready.

---

### Billing (259,081 records)

| Field | Fill Rate | Status |
|---|---|---|
| patient_id | 100.0% | Ready |
| encounter_id | 100.0% | Ready |
| bill_number | 100.0% | Ready |
| subtotal | 100.0% | Ready (but 33,575 = ₦0) |
| discount | 100.0% | Ready (mostly ₦0) |
| hmo_covered | 100.0% | Ready (mostly ₦0) |
| payment_method | 0.0% | Gap — not in Hope |
| status | 100.0% | Ready (99.9% pending) |
| billed_at | 100.0% | Ready |
| paid_at | 0.0% (14 records) | Gap — not in Hope |

**Anomalies:**
- 33,575 bills with ₦0 subtotal (13% of all bills) — likely zero-rated services or data entry blanks in Hope
- 3 bills with negative `patient_balance` — rounding or discount overrun
- Average bill where subtotal > 0: **₦7,690.38**

---

### Appointments (253,402 records)

| Field | Fill Rate | Status |
|---|---|---|
| patient_id | 100.0% | Ready |
| slot_id | 100.0% | Ready |
| encounter_id | 0.0% | Expected — set on patient arrival |
| reason | 0.0% (106 records) | Gap — not in Hope |
| status | 100.0% | Ready |
| booked_by | 100.0% | Ready |

---

## 7. Foreign Key Validation Results

**All 11 FK paths: 0 broken references.**

The ingest pipeline's patient-ID remapping step (which deduplicated 339,471 Hope patient rows into 60,935 canonical IDs) worked correctly. Every child record points to a valid parent.

---

## 8. Production Readiness Assessment

### Ready for Production Use

| Dataset | Records | Why Ready |
|---|---|---|
| Patient identity | 60,935 | Name, MRN, DOB, gender all complete |
| Prescriptions | 258,635 | All fields populated; full FK chain |
| Appointment bookings | 253,402 | Patient + slot linked; status set |
| Billing records | 259,081 | Bill numbers, amounts, dates present |
| Lab order workflow | 203,538 | FK chain complete; test codes present |

### Requires Enrichment Before Clinical Use

| Dataset | Records | What's Missing | How to Fix |
|---|---|---|---|
| Lab test names | 203,521 | Real test names (100% placeholder) | Discover Hope `laboratory` catalog table; join via `test_code`; re-map |
| Encounter doctors | 518,472 | consulting_doctor = blank | Import Hope staff table; resolve `consultant_sb` FK |
| Encounter triage | 518,471 | triage_level, triage_notes, triage_at = blank | Map Hope `diagnoses.triage_*` columns in admission transformer |
| Encounter discharge | 518,472 | discharge_at, discharge_summary = blank | Map Hope `diagnoses.discharge_*` or `admissions.date_discharged` |
| Patient demographics | 60,935 | Phone 1%, email 4%, address/NOK/blood/HMO = 0% | Patient portal self-registration + front-desk intake |
| Ward/bed tracking | 0 | royan_wards + royan_beds empty | Seed ward master from department names + Hope ward data |

### Permanently Limited by Hope's Schema

| Dataset | Why It Won't Fill From Hope | What to Do |
|---|---|---|
| Lab results (17 records) | Hope doesn't export individual result values | Live lab module will populate |
| Vital signs (17 records) | Hope doesn't track vitals | Live nursing module will populate |
| Dispensing records (0) | Hope has no dispensing transaction table | Live pharmacy workflow will populate |
| Insurance claims (0) | Hope doesn't track claim status | Live HMO billing workflow will populate |
| Payment transactions (14) | Hope only stores totals, not payment events | Live cashier module will populate |
| Encounter notes (19) | Hope doesn't have structured SOAP notes | Doctors will write in live system |
| HMO/insurance tables (0) | No HMO enrollment data in Hope dump | Onboard HMO providers via admin panel |

---

## 9. Top Findings & Recommended Actions

| Priority | Finding | Action |
|---|---|---|
| P0 | 203,521 lab orders say "Imported lab order" | Connect to Hope MySQL → `DESCRIBE laboratory_test_orders` → identify real test name column → update `LAB_MAP` in `field_maps.py` → re-run `--from-staging` |
| P1 | 518,472 encounters have no consulting doctor | Import Hope staff/consultant table → resolve `consultant_sb` FK in admission transformer |
| P1 | Encounters have no triage or discharge data | Map Hope `diagnoses.triage_*` + `date_discharged` columns |
| P2 | royan_wards + royan_beds empty | Seed from known ward names (5 departments extractable + Hope ward master if available) |
| P2 | 33,575 bills with ₦0 subtotal | Investigate Hope `service_bills` for these encounter IDs — may need manual zero-rating flag |
| P3 | 172 doctor names in lab orders not in staff table | Extract distinct `ordered_by` values → bulk-create staff records |
| P3 | Payment method 0% on all bills | Will fill via live cashier; no fix needed from Hope |
| P4 | 102 same name+DOB patient combos | Manual review; no system action required |

---

*Report generated from live `synbot_health` PostgreSQL database — royan_db Docker container.*  
*Audit script: `data_quality_audit.py`*
