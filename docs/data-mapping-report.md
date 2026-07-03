# RoyanHealth — Hope Data Mapping Report

**Source:** DRM Hope MySQL  
**Destination:** RoyanHealth PostgreSQL  
**Last Ingest:** 2026-06-24

---

## Import Summary

| Entity | Table | Records Imported |
|---|---|---|
| Patients | `royan_patients` | 60,927 |
| Appointments | `royan_appointments` | 253,401 |
| Admissions | `royan_encounters` | 256,452 |
| Lab Orders | `royan_lab_orders` | 203,521 |
| Prescriptions | `royan_prescriptions` | 258,618 |
| Billing | `royan_billing` | 251,986 |
| **Total** | | **1,284,905** |

---

## 1 · Patients

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `mrn` | text | `patient_id`, `mrn`, `hospital_no`, `file_no`, `patient_no` |
| `first_name` | text | `first_name`, `fname`, or split from `full_name` / `patient_name` |
| `last_name` | text | `last_name`, `lname`, `surname`, or split from `full_name` |
| `date_of_birth` | date | `date_of_birth`, `dob`, `birth_date` |
| `gender` | text | `gender`, `sex` |
| `phone` | text | `phone`, `mobile`, `telephone`, `phone_no` |
| `email` | text | `email` |
| `address` | text | `address`, `address1` |
| `next_of_kin_name` | text | `next_of_kin`, `nok_name`, `emergency_contact`, `guardian` |
| `next_of_kin_phone` | text | `nok_phone`, `emergency_phone`, `nok_mobile` |
| `blood_group` | text | `blood_group`, `bloodgroup`, `blood_type` |
| `genotype` | text | `genotype` |
| `allergies` | text[ ] | `allergies`, `allergy` |
| `hmo_provider` | text | `hmo`, `insurance`, `insurance_name`, `hmo_name` |
| `hmo_id` | text | `hmo_id`, `membership_no`, `policy_no`, `member_no` |
| `registered_at` | timestamp | `registration_date`, `reg_date`, `created_at` |
| `external_id` | text | Hope original patient ID (sync key) |

> **Gaps:** `email`, `address`, `next_of_kin_*`, `genotype`, `allergies` — frequently blank in Hope exports.

---

## 2 · Appointments

### Slot (time block)

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `doctor_name` | text | `doctor`, `doctor_name`, `physician`, `consultant` |
| `department` | text | `department`, `dept`, `clinic` |
| `slot_date` | date | `appointment_date`, `appt_date`, `visit_date`, `schedule_date` |
| `slot_time` | time | `appointment_time`, `appt_time`, `start_time`, `schedule_time` |

### Appointment (booking)

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `patient_id` | FK → patients | matched via Hope `patient_id` |
| `reason` | text | `reason`, `reason_for_visit`, `complaint`, `purpose` |
| `status` | text | `status`, `appt_status` |
| `external_id` | text | `appointment_id`, `appt_id` |

> **Gaps:** Slot linkage (date + time + doctor) is inferred — may produce duplicates if Hope has multiple bookings at the same slot.

---

## 3 · Admissions / Encounters

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `patient_id` | FK → patients | matched via Hope `patient_id` |
| `encounter_type` | text | derived from Hope context (inpatient / outpatient / emergency) |
| `department` | text | `department`, `dept` |
| `chief_complaint` | text | `complaints`, `presenting_complaint` |
| `consulting_doctor` | text | `consultant`, `doctor`, `physician`, `attending_doctor` |
| `triage_level` | text | `triage_level`, `triage`, `triage_score`, `triage_category` |
| `triage_notes` | text | `triage_notes`, `triage_complaint` |
| `triage_at` | timestamp | `triage_at`, `triage_time`, `triage_date` |
| `triage_by` | text | `triage_by`, `triage_nurse` |
| `diagnosis_notes` | text | `diagnosis`, `final_diagnosis`, `icd_code`, `icd10_code` |
| `discharge_summary` | text | `discharge_summary`, `discharge_notes` |
| `discharge_at` | timestamp | `discharge_date`, `date_discharged`, `discharged_at` |
| `ward` | FK → wards | resolved from `_ward_name` |
| `bed` | FK → beds | resolved from `_bed_label` |
| `external_id` | text | `admission_id`, `admit_id` |

> **Gaps:** Triage fields, ward/bed assignments — depend on Hope having structured triage data.

---

## 4 · Lab Orders

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `patient_id` | FK → patients | matched via Hope `patient_id` |
| `encounter_id` | FK → encounters | extracted from Hope diagnosis records |
| `test_name` | text | `test_name`, `investigation`, `lab_test`, `description`, `service_name`, `item_name` |
| `test_code` | text | `laboratory_id`, `test_code` |
| `urgency` | text | `urgency`, `priority` |
| `status` | text | `labdash_status`, `status`, `lab_status` |
| `ordered_by` | text | `doctor_id`, `ordered_by`, `requesting_doctor` |
| `ordered_at` | timestamp | `lab_order_date`, `order_date`, `request_date`, `created_at` |
| `sample_type` | text | `sample_type`, `specimen`, `specimen_type` |
| `notes` | text | `result_summary`, `result`, `findings`, `comments` |
| `external_id` | text | `lab_id`, `order_id`, `request_id` |

> **Gaps:** `test_name` falls back to `"Imported lab order"` when Hope has no value in any mapped field — affects ~203,000 records. `sample_collected_at` is never populated from Hope.

---

## 5 · Prescriptions

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `patient_id` | FK → patients | matched via Hope `patient_id` |
| `encounter_id` | FK → encounters | via Hope `diagnosis_id` |
| `drug_name` | text | `drug_name`, `drug`, `medication`, `item_name`, `product_name` |
| `drug_code` | text | `drug_code`, `nafdac_no`, `drug_id` |
| `dosage` | text | `dosage`, `dose`, `strength`, `tabs_per_day` |
| `frequency` | text | `frequency`, `dosage_frequency`, `tabs_frequency` |
| `duration` | text | `duration`, `days` |
| `route` | text | `route`, `route_of_admin`, `mode` |
| `quantity` | numeric | `quantity`, `qty`, `qty_dispensed` |
| `unit` | text | `unit`, `unit_of_measure`, `form` |
| `special_instructions` | text | `instructions`, `special_instructions` |
| `prescribed_by` | text | `prescribed_by`, `doctor`, `prescriber` |
| `prescribed_at` | timestamp | `prescribed_at`, `order_date`, `created_at` |
| `status` | text | `status` |
| `external_id` | text | `prescription_id`, `dispense_id`, `order_id` |

> **Gaps:** Good overall coverage. `route` defaults to `"oral"` when blank in Hope.

---

## 6 · Billing

> Hope stores billing as a single flat total. RoyanHealth splits it into charge categories. The breakdown is estimated — exact charge splits require Hope's service billing tables.

| RoyanHealth Column | Data Type | Maps From (Hope Field) |
|---|---|---|
| `patient_id` | FK → patients | matched via Hope `patient_id` |
| `bill_number` | text | `bill_number`, `bill_code` |
| `consultation_fee` | numeric | broken out from `total_amount`, `gross_amount` |
| `lab_charges` | numeric | broken out from `total_amount` |
| `pharmacy_charges` | numeric | broken out from `total_amount` |
| `ward_charges` | numeric | broken out from `total_amount` |
| `procedure_charges` | numeric | `service_charge`, `charge` |
| `subtotal` | numeric | **auto-calculated** (sum of all charges) |
| `discount` | numeric | `discount` |
| `hmo_covered` | numeric | `hmo_amount`, `insurance_amount`, `covered_amount` |
| `patient_balance` | numeric | **auto-calculated** (subtotal − discount − hmo_covered) |
| `status` | text | `status`, `payment_status` |
| `payment_method` | text | `payment_method`, `pay_method`, `mode_of_payment` |
| `billed_at` | timestamp | `invoice_date`, `bill_date`, `created_at` |
| `notes` | text | `notes`, `remarks` |
| `external_id` | text | `invoice_id`, `bill_id`, `transaction_id` |

> **Gaps:** Charge breakdown not available in Hope — all imported into a flat total. `paid_at` never populated from Hope.

---

## Coverage Summary

| Entity | Mapping Quality | Biggest Gap |
|---|---|---|
| Patients | High | Email, next-of-kin, genotype often blank |
| Appointments | Medium | Slot linkage inferred from date/time/doctor |
| Admissions | Medium | Triage and ward/bed data often missing |
| Lab Orders | Low | test_name blank for ~100% of records |
| Prescriptions | High | Minor — route defaults |
| Billing | Medium | Charge breakdown not split in Hope |

---

## How to Fix a Mapping Gap

All field mappings live in one file:

```
data-assimilation/transformers/field_maps.py
```

Each entity has a `*_MAP` dictionary. To add a new Hope column, add it as a key pointing to the RoyanHealth column name, then re-run the ingest:

```bash
cd data-assimilation
python ingest.py --source dump --from-staging
```

No database schema changes needed.
