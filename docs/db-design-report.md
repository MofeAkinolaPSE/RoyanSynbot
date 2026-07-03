# RoyanHealth PostgreSQL — Database Design Report
**Perspective:** RoyanHealth system (not Hope source fields)  
**Last updated:** 2026-06-26  
**Total tables:** 42 across 5 layers

---

## Architecture Overview

The database is structured in layers, each with a distinct purpose:

```
┌──────────────────────────────────────────────────────┐
│  BRONZE (Source)                                     │
│  SQLite staging DB — raw Hope rows, unchanged        │
│  hope_staging.db  (local, not in Postgres)           │
└──────────────────┬───────────────────────────────────┘
                   │  ingest pipeline
┌──────────────────▼───────────────────────────────────┐
│  SILVER (Operational)                                │
│  Cleaned, structured, FK-linked clinical data        │
│  royan_patients, royan_encounters, royan_lab_orders  │
│  royan_prescriptions, royan_billing, royan_appts...  │
└──────────────────┬───────────────────────────────────┘
                   │  aggregation
┌──────────────────▼───────────────────────────────────┐
│  GOLD (Analytics)                                    │
│  Denormalised fact + dimension tables for reporting  │
│  dim_patient, fact_queue_visits, fact_billing_summary│
└──────────────────────────────────────────────────────┘
```

Every Silver table that receives Hope data carries three sync columns:

| Column | Purpose |
|---|---|
| `external_source` | Always `"hope"` for Hope-imported rows |
| `external_id` | Hope's original row ID (ensures idempotent upsert) |
| `external_updated_at` | Timestamp of the Hope record at time of import |

---

## Layer 1 — Core Clinical Tables (Silver, Populated from Hope)

### royan_patients
**60,927 records** · Root of the entire schema — every other clinical table FK-references this.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | Auto-generated, used as FK target by 22 other tables |
| `mrn` | text UNIQUE | Medical Record Number — format: `RH16-27` (from Hope) |
| `first_name` | text NOT NULL | |
| `last_name` | text NOT NULL | |
| `date_of_birth` | date | 99% filled |
| `gender` | text | male/female/other/prefer_not_to_say |
| `phone` | text | 1% filled from Hope |
| `email` | text | 4% filled from Hope |
| `address` | text | Empty — not in Hope data |
| `next_of_kin_name` | text | Empty — not in Hope data |
| `next_of_kin_phone` | text | Empty — not in Hope data |
| `blood_group` | text | Empty — not in Hope data |
| `genotype` | text | AA/AS/SS/AC/SC/unknown |
| `allergies` | text[] | Empty — not in Hope data |
| `hmo_provider` | text | Empty — not in Hope data |
| `hmo_id` | text | Empty — not in Hope data |
| `is_active` | boolean DEFAULT true | |
| `registered_by` | text | Staff username who registered |
| `registered_at` | timestamptz | From Hope registration_date |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's patient_id (integer, e.g. `1`, `24`, `7`) |

**Indexes:** mrn, phone, lower(last_name), hmo_id, (external_source, external_id) UNIQUE

---

### royan_encounters
**518,460 records** · One row per hospital visit — covers outpatient, inpatient, emergency, maternity, surgical.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `patient_id` | bigint FK → royan_patients | |
| `encounter_type` | text NOT NULL | outpatient/inpatient/emergency/maternity/surgical |
| `status` | text DEFAULT 'patient_registered' | patient_registered → triaged → consulting → lab_ordered → pharmacy_dispensing → billing_pending → discharged |
| `department` | text | A&E, OPD, Inpatient Ward, Maternity, Surgery, etc. |
| `triage_level` | text | immediate/urgent/less_urgent/non_urgent |
| `triage_notes` | text | |
| `triage_at` | timestamptz | |
| `triage_by` | text | Staff name/ID |
| `chief_complaint` | text | Patient's presenting complaint |
| `consulting_doctor` | text | Doctor name |
| `consultation_at` | timestamptz | |
| `diagnosis_codes` | text[] | ICD-10 codes |
| `diagnosis_notes` | text | |
| `discharge_summary` | text | |
| `discharge_at` | timestamptz | |
| `discharge_by` | text | |
| `ward_id` | bigint FK → royan_wards | Nullable |
| `bed_id` | bigint FK → royan_beds | Nullable |
| `queue_number` | text | e.g. `OPD-001` — assigned on check-in |
| `called_at` | timestamptz | When patient was called from waiting room |
| `consulting_room` | varchar(50) | |
| `nurse_done_at` | timestamptz | |
| `registered_by` | text | |
| `created_at` | timestamptz | |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's admission_id |

**Indexes:** patient_id, status, created_at DESC, department, queue_number, (external_source, external_id) UNIQUE

---

### royan_appointments
**253,402 records** · Patient bookings into doctor slots.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `patient_id` | bigint FK → royan_patients | |
| `slot_id` | bigint FK → royan_appointment_slots | The time block booked |
| `encounter_id` | bigint FK → royan_encounters | Set when patient arrives |
| `reason` | text | Reason for visit |
| `status` | text DEFAULT 'booked' | booked/confirmed/arrived/completed/no_show/cancelled/rescheduled |
| `booked_by` | text | Staff or `"patient_self"` |
| `booked_at` | timestamptz | |
| `reminder_sent` | boolean DEFAULT false | |
| `cancellation_reason` | text | |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's appointment_id |

**Indexes:** patient_id, slot_id, status, booked_at DESC, (external_source, external_id) UNIQUE

---

### royan_appointment_slots
Linked to royan_appointments. One row per available time block.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `doctor_name` | text NOT NULL | |
| `department` | text NOT NULL | |
| `slot_date` | date NOT NULL | |
| `slot_time` | time NOT NULL | |
| `duration_mins` | int DEFAULT 15 | |
| `is_available` | boolean DEFAULT true | |
| `max_patients` | int DEFAULT 1 | |
| `external_source` | text | `"hope"` |
| `external_id` | text | |

**Constraint:** UNIQUE (doctor_name, slot_date, slot_time)

---

### royan_lab_orders
**203,521 records** · Lab test requests ordered per encounter.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `patient_id` | bigint FK → royan_patients | |
| `encounter_id` | bigint FK → royan_encounters | |
| `test_name` | text NOT NULL | ~100% show `"Imported lab order"` — Hope had no test name field |
| `test_code` | text | |
| `urgency` | text DEFAULT 'routine' | routine/urgent/stat |
| `status` | text DEFAULT 'ordered' | ordered/sample_collected/processing/resulted/cancelled |
| `ordered_by` | text NOT NULL | Doctor name/ID |
| `ordered_at` | timestamptz NOT NULL | |
| `sample_type` | text | Specimen type |
| `sample_collected_at` | timestamptz | Not populated from Hope |
| `notes` | text | Result summary / findings |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's lab_id / order_id |

**Indexes:** encounter_id, patient_id, status, (external_source, external_id) UNIQUE

---

### royan_prescriptions
**258,618 records** · Drug prescriptions written per encounter.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `patient_id` | bigint FK → royan_patients | |
| `encounter_id` | bigint FK → royan_encounters | |
| `drug_name` | text NOT NULL | |
| `drug_code` | text | NAFDAC/formulary code |
| `dosage` | text NOT NULL | e.g. `"500mg"` |
| `frequency` | text NOT NULL | e.g. `"8 hourly"` |
| `duration` | text | e.g. `"5 days"` |
| `route` | text DEFAULT 'oral' | oral/iv/im/topical/inhaled/sublingual/rectal/other |
| `quantity` | numeric NOT NULL DEFAULT 1 | |
| `unit` | text DEFAULT 'tablet' | |
| `special_instructions` | text | |
| `prescribed_by` | text NOT NULL | Doctor name/ID |
| `prescribed_at` | timestamptz NOT NULL | |
| `status` | text DEFAULT 'pending' | pending/dispensed/partially_dispensed/cancelled/returned |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's prescription_id / dispense_id |

**Indexes:** encounter_id, patient_id, status, (external_source, external_id) UNIQUE

---

### royan_billing
**251,986 records** · One bill per encounter with itemised charge buckets.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `patient_id` | bigint FK → royan_patients | |
| `encounter_id` | bigint FK → royan_encounters | |
| `bill_number` | text UNIQUE | |
| `consultation_fee` | numeric DEFAULT 0 | |
| `lab_charges` | numeric DEFAULT 0 | |
| `pharmacy_charges` | numeric DEFAULT 0 | |
| `ward_charges` | numeric DEFAULT 0 | |
| `procedure_charges` | numeric DEFAULT 0 | |
| `miscellaneous` | numeric DEFAULT 0 | |
| `subtotal` | numeric GENERATED | Auto-sum of all charge columns |
| `discount` | numeric DEFAULT 0 | |
| `hmo_covered` | numeric DEFAULT 0 | Amount paid by HMO |
| `patient_balance` | numeric GENERATED | subtotal − discount − hmo_covered |
| `status` | text DEFAULT 'pending' | pending/partial/paid/waived/disputed/written_off |
| `payment_method` | text | cash/card/transfer/hmo/waiver/mixed |
| `billed_by` | text | |
| `billed_at` | timestamptz | |
| `paid_at` | timestamptz | Not populated from Hope |
| `external_source` | text | `"hope"` |
| `external_id` | text | Hope's invoice_id / bill_id |

**Indexes:** encounter_id, patient_id, status, billed_at DESC, (external_source, external_id) UNIQUE

---

## Layer 2 — Child Tables (Silver, Empty — Awaiting Live Data)

These tables are fully defined and FK-linked but have 0 records because Hope didn't provide this level of data. They fill once the live system is in use.

| Table | Records | Purpose |
|---|---|---|
| `royan_lab_results` | 0 | Test results per lab order (result_data, interpretation, reference range) |
| `royan_dispensing` | 0 | Pharmacy dispense records per prescription (batch, expiry, quantity_dispensed) |
| `royan_payments` | 0 | Individual payment transactions per bill (supports partial payments) |
| `royan_insurance_claims` | 0 | HMO claim submissions per bill (authorisation_code, approved_amount) |
| `royan_encounter_notes` | 0 | SOAP/progress/discharge notes per encounter |
| `royan_vitals` | 0 | Vital signs per encounter (BP, temp, pulse, SpO2, weight, BMI) |
| `royan_nursing_care_plans` | 0 | Nursing care plans per patient/encounter |
| `royan_fluid_balance` | 0 | Fluid intake/output records for inpatients |
| `royan_allergies` | 0 | Patient allergy records (allergen, reaction, severity) |
| `royan_consent_records` | 0 | Consent documentation per encounter |
| `royan_problem_list` | 0 | Active diagnosis/problem list per patient |
| `royan_mar_entries` | 0 | Medication administration records (who gave what, when) |

---

## Layer 3 — HMO & Service Catalog

These tables support insurance/coverage workflows. All empty until HMO providers are onboarded.

| Table | Purpose |
|---|---|
| `royan_hmos` | HMO provider registry (NHIS, AXA Mansard, etc.) |
| `royan_hmo_plans` | Plans per HMO (e.g. Comprehensive, Essential) |
| `royan_patient_insurance` | Patient HMO enrolment (links patient ↔ HMO plan) |
| `royan_service_catalog` | Hospital services with codes and base prices |
| `royan_coverage_rules` | What each HMO covers per service (percent/fixed/capitation) |
| `royan_coverage_authorizations` | Pre-auth requests and approvals per encounter |
| `royan_bill_items` | Itemised line items on bills (service_code, quantity, unit_price) |

---

## Layer 4 — Analytics (Gold Layer)

Denormalised tables optimised for reporting dashboards. Populated by a separate aggregation job, not the Hope ingest.

| Table | Purpose |
|---|---|
| `dim_patient` | Patient dimension — one row per patient with age_band, hmo_provider |
| `dim_service` | Service catalog snapshot for analytics joins |
| `dim_staff` | Staff snapshot for analytics |
| `dim_time` | Date spine 2020–2030 (day, week, month, quarter, year, is_weekend) |
| `fact_queue_visits` | One row per encounter — wait_minutes, consult_minutes, total_visit_minutes (partitioned by year) |
| `fact_billing_summary` | One row per bill — all charge buckets + hmo_covered + patient_balance (partitioned by year) |
| `royan_operations_events` | Audit/deviation/maintenance events (polymorphic) |

---

## Layer 5 — Staff & Operations

| Table | Records | Purpose |
|---|---|---|
| `royan_staff` | — | Staff registry (staff_number, department, designation, monthly_gross) |
| `royan_timesheets` | — | Attendance: clock_in/out, shift, overtime, absence |
| `royan_procurement_shipments` | — | Supplier shipments, PO tracking, performance metrics |
| `royan_import_jobs` | — | ETL job ledger (batch_id, status, retention_days) |
| `royan_gl_snapshot` | — | General Ledger P&L entries from financial imports |

---

## Sync Tracking Table

### royan_hope_sync_runs
One row per ingest run. Records what ran, how many rows, and whether it succeeded.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `entity` | text | e.g. `"patients"`, `"lab"`, `"billing"` |
| `status` | text | started/success/failed |
| `started_at` | timestamptz | |
| `completed_at` | timestamptz | |
| `rows_seen` | int | Rows read from staging |
| `rows_upserted` | int | Rows written to Postgres |
| `error_message` | text | Populated if status = failed |
| `ingest_mode` | text | bulk_import (dump) / live_bridge (ODBC) |
| `metadata` | jsonb | Extra context |

---

## Foreign Key Map

```
royan_patients (id)
│
├── royan_encounters (patient_id)
│   ├── royan_lab_orders (encounter_id)
│   │   └── royan_lab_results (lab_order_id)
│   ├── royan_prescriptions (encounter_id)
│   │   ├── royan_dispensing (prescription_id)
│   │   └── royan_mar_entries (prescription_id)
│   ├── royan_billing (encounter_id)
│   │   ├── royan_payments (billing_id)
│   │   ├── royan_insurance_claims (billing_id)
│   │   └── royan_bill_items (billing_id)
│   ├── royan_encounter_notes (encounter_id)
│   ├── royan_vitals (encounter_id)
│   ├── royan_nursing_care_plans (encounter_id)
│   ├── royan_fluid_balance (encounter_id)
│   ├── royan_consent_records (encounter_id)
│   ├── royan_problem_list (encounter_id)
│   ├── royan_mar_entries (encounter_id)
│   ├── royan_coverage_authorizations (encounter_id)
│   └── fact_queue_visits (encounter_id)
│
├── royan_appointments (patient_id)
│   └── royan_appointment_slots (slot_id)
│
├── royan_patient_insurance (patient_id)
├── royan_allergies (patient_id)
├── royan_coverage_authorizations (patient_id)
├── dim_patient (patient_id)
└── fact_billing_summary (via billing → encounters → patient)

royan_hmos (id)
├── royan_hmo_plans (hmo_id)
│   └── royan_coverage_rules (plan_id)
│       └── royan_bill_items (coverage_rule_id)
└── royan_patient_insurance (hmo_id)

royan_service_catalog (id)
└── royan_coverage_rules (service_id)
    └── royan_bill_items (service_id)
```

---

## Current Population Summary

| Layer | Populated | Empty |
|---|---|---|
| Core clinical (Silver) | patients, encounters, appointments, lab orders, prescriptions, billing | — |
| Child clinical | — | lab results, dispensing, payments, claims, notes, vitals, care plans, fluids, allergies, consent, problem list, MAR |
| HMO & coverage | — | All 7 tables |
| Analytics (Gold) | dim_time | dim_patient, dim_service, dim_staff, fact tables |
| Staff & ops | — | All 5 tables |
