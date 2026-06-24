# SynbotHealth — Royan Hospital Implementation Plan v2
**Client:** Royan Hospital | **IT Lead:** Seun Akinkla, Head of IT/Systems
**Date:** 2026-05-28 | **Go-Live Target:** Within 1 month (ASAP)
**Reference Architecture:** VistA (WorldVistA) — Hospital Operating System blueprint

---

## 0. Executive Summary

Royan Hospital requires an AI-native Hospital Operating System covering ~20 clinical and operational domains. The go-live is **within 1 month on an on-premise server**, with a MySQL/MariaDB legacy system (DRM Hope) that must remain in read-sync via Hope Bridge.

**Hospital Profile:**
- 20–50 inpatient beds, 81–150 OPD visits/day, <10 A&E/day
- 10+ HMO providers (NHIS + private)
- On-premise deployment, not cloud

**VistA Design Principle (anchor for all decisions):**
```
Patient → Encounter → Orders → Results → Actions → Audit
```
Every feature must trace back to this flow. This is not an app — it is a **Hospital Operating System**.

---

## 1. Requirements → VistA Module Mapping

| Client Requirement Area | VistA Reference Module | Current Status |
|---|---|---|
| Registration / MRN | ADT (Admission-Discharge-Transfer) | Partial — MRN auto-gen done, no duplicate detection |
| Queue / Scheduling | Scheduling Module | Partial — queue exists, no SMS/specialty scheduling |
| A&E Workflow | ADT + Emergency | Missing — ED-to-ward flow not built |
| Inpatient / Ward | Nursing Module + Bed Management | Missing — ward rounds, MAR, vitals, fluid balance |
| Clinical Documentation | TIU (Text Integration Utilities) | Partial — encounter notes added, no SOAP/ICD-10 |
| Lab | Lab/LOINC Module | Partial — order/results UI done, no reference ranges/LOINC |
| Radiology | Clinical Procedures / Imaging | MISSING entirely |
| Pharmacy | BCMA + Pharmacy Module | Partial — dispensing UI done, no DDI/allergy/inventory |
| Nursing | Nursing Module | MISSING — vitals, care plan, wound, pain scores |
| Surgical Theatre | OR (Operating Room) | MISSING entirely |
| MCH / OB-GYN | Women's Health Module | MISSING entirely |
| Specialist Clinics | Scheduling + TIU templates | MISSING — specialty templates |
| Billing | Accounts Receivable + Fee Schedule | Partial — basic billing done, no inpatient running bill |
| Medical Records | TIU + Document Management | Missing — document scan, referral letters, audit log |
| Quality / Safety | Clinical Reminders + Adverse Reaction | Missing |
| HR | HR Module | Missing — scheduling, leave, payroll |
| Digital Patient Engagement | Patient Portal / Messaging | MISSING entirely |
| Reporting | NHIA/HMIS Export | Missing |
| Integrations | Paystack, PACS | Missing |
| Hope Bridge | Legacy Sync | Done — MySQL confirmed, 9 modules |

---

## 2. Gap Analysis — Current vs. Required

### Already Built (Green)
- Patient registration with auto-MRN
- Clinical queue with encounter lifecycle (patient_registered → triaged → consulting → discharged)
- Lab order management (create, result, status workflow)
- Pharmacy dispensing (list Rx, dispense, cancel)
- Hospital billing (create bill, HMO claim)
- HMO Admin (NHIS + private HMO management)
- Ward & Bed management (bed allocation, occupancy)
- Appointments (calendar, day view, next-slot)
- Doctor Dashboard (filtered by JWT identity)
- Patient profile with encounter timeline
- AlertBanner + InlineWarning components
- Encounter notes (SOAP-ready endpoint, general/assessment/plan types)
- Sidebar live badges
- AskSynbot clinical + executive mode
- Hope Bridge sync (MySQL → Supabase)
- HMO coverage engine (billing rules)

### Missing / Partial — Must Build

#### Priority 5 (CRITICAL — Client marked all these)

**P5-1: Duplicate Detection at Registration**
- Alert when name + DOB or phone matches an existing patient
- Block or warn on potential duplicate MRN creation

**P5-2: Consent Forms**
- Digital consent capture at registration
- Store PDF/structured data per encounter

**P5-3: QR Kiosk Check-in**
- Generate QR per patient → scan on arrival → auto-register to queue

**P5-4: SMS Reminders for Appointments**
- Twilio / Africa's Talking integration
- Fire on appointment creation and 24h before

**P5-5: Specialty Scheduling**
- Department-level slot management
- Doctor-specific availability calendars

**P5-6: Clinical Documentation (Full SOAP + ICD-10 + Problem List)**
- Structured SOAP note editor
- ICD-10 diagnosis code selector
- Problem list with active/inactive/resolved states
- Copy-forward previous note template

**P5-7: Lab Enhancements**
- Reference ranges per test (normal / abnormal / critical)
- Cumulative result history (trending view)
- LOINC code mapping
- Send-out (external lab) tracking

**P5-8: Pharmacy Enhancements**
- Drug inventory management
- Drug-Drug Interaction (DDI) checking
- Allergy checking at dispense time
- Ward stock replenishment requests

**P5-9: Radiology Module (COMPLETE — zero implementation exists)**
- Imaging request (X-ray, ultrasound, CT, MRI)
- Worklist (pending/completed scans)
- Report entry by radiologist
- ECG / Echo documentation
- TAT (turnaround time) monitoring
- PACS integration stub

**P5-10: Nursing Module (COMPLETE — zero implementation exists)**
- Vitals recording (BP, temp, pulse, SpO2, RR, weight, height, BSL)
- Nursing care plan
- Pain score assessment
- Wound care documentation
- Fluid balance chart
- Shift handover notes

**P5-11: Inpatient Ward Management**
- Ward round documentation
- MAR (Medication Administration Record)
- Fluid balance chart
- Nursing care plans per patient

**P5-12: Surgical Theatre (COMPLETE — zero implementation exists)**
- Theatre scheduling (elective + emergency)
- Pre-op assessment checklist
- Anaesthetic record
- Operative notes
- Post-op recovery tracking
- Theatre utilisation report

**P5-13: MCH / OB-GYN (COMPLETE — zero implementation exists)**
- ANC (Antenatal Care) booking + visit tracking
- Partograph (labour progress)
- Delivery record
- Newborn assessment
- Immunisation schedule
- Family planning records

**P5-14: Specialist Clinic Templates**
- 14 specialty templates (Cardiology, ENT, Ophthalmology, Dermatology, Orthopaedics, etc.)
- Template-based structured notes
- Specialty-specific order sets

**P5-15: Billing Enhancements**
- Inpatient running bill (accumulate charges per admission)
- Fee schedule management
- Indigent patient tracking / subsidy flags

**P5-16: Medical Records Management**
- Document scanning upload (PDF, image)
- Referral letter generation (template)
- Full audit log viewer (who did what, when)

**P5-17: Quality & Safety**
- Incident report (RCA — Root Cause Analysis)
- Infection control log
- HEFAMAA compliance checklist

**P5-18: HR Module**
- Staff scheduling / shift roster
- Leave management
- Basic payroll integration stub

**P5-19: Digital Patient Engagement (ENTIRELY MISSING)**
- Patient portal (web app / PWA)
- WhatsApp notifications (via Twilio or Meta API)
- Telemedicine (video consult link)

**P5-20: Reporting & Export**
- NHIA/HMIS export (government reporting format)
- Disease burden analytics
- Operational summary reports

**P5-21: Payment Integrations**
- Paystack payment gateway
- Flutterwave payment gateway

---

## 3. Implementation Phases

### Phase 1 — Foundation Hardening (Week 1)
*Make existing modules production-ready for the hospital's Day 1*

| # | Feature | VistA Ref | Backend | Frontend |
|---|---|---|---|---|
| 1.1 | Duplicate patient detection | ADT | `POST /patients` — fuzzy match before insert | Warning dialog at registration |
| 1.2 | Consent form capture | ADT / TIU | `royan_consent_records` table + `POST /patients/{id}/consent` | Consent step in registration flow |
| 1.3 | ICD-10 diagnosis selector in encounter | TIU | `royan_icd10_codes` lookup table + `PATCH /queue/encounters/{id}` accepts `icd10_codes[]` | Autocomplete ICD-10 in consultation step |
| 1.4 | Problem list | CPRS | `royan_problem_list` table + CRUD endpoints | Problem list tab in PatientProfile |
| 1.5 | Copy-forward last note | TIU | `GET /queue/encounters/{id}/notes?last=true` | "Copy last note" button in notes editor |
| 1.6 | Inpatient running bill | AR | `royan_inpatient_bill_lines` table — append charges per admission | Running bill tab in HospitalBilling |
| 1.7 | Fee schedule management | AR | `royan_fee_schedule` table + admin CRUD | Fee schedule page under Admin |
| 1.8 | Audit log viewer | All | Read from existing Supabase audit_events | Audit Log page under Admin/Medical Records |

---

### Phase 2 — Clinical Modules I: Lab + Pharmacy + Nursing (Week 1-2)

| # | Feature | VistA Ref | Backend | Frontend |
|---|---|---|---|---|
| 2.1 | Lab reference ranges | Lab/LOINC | `royan_lab_reference_ranges` table — per test, normal/critical ranges | Inline normal/critical range display in results |
| 2.2 | Cumulative lab history | Lab | `GET /lab/patients/{patient_id}/history?test_name=X` | Trend chart in PatientProfile Labs tab |
| 2.3 | LOINC code mapping | Lab/LOINC | Add `loinc_code` column to `royan_lab_orders` | LOINC shown alongside test name |
| 2.4 | Send-out lab tracking | Lab | `status = "sent_out"` + `external_lab` field | Send-out filter + status badge |
| 2.5 | Drug inventory | Pharmacy | `royan_drug_inventory` table + stock movement endpoints | Inventory tab in PharmacyDispensing |
| 2.6 | DDI checking | BCMA | `royan_drug_interactions` lookup + check at dispense | Warning popup at Dispense action |
| 2.7 | Allergy check at dispense | BCMA + Adverse Reaction | Check `royan_allergies` against prescribed drug | Block/warn on dispense if allergy match |
| 2.8 | Ward stock replenishment | Pharmacy | `POST /pharmacy/replenishment-request` | Replenishment request form from ward |
| 2.9 | Vitals recording | Nursing | `royan_vitals` table + `POST /nursing/encounters/{id}/vitals` | Vitals entry form in ClinicalQueue encounter view |
| 2.10 | Nursing care plan | Nursing | `royan_nursing_care_plans` table | Care plan tab in ward/encounter view |
| 2.11 | Pain score | Nursing | Column on vitals record: `pain_score (0-10)` | Pain score slider in vitals form |
| 2.12 | Fluid balance | Nursing | `royan_fluid_balance` table (intake/output per shift) | Fluid balance chart in ward view |

---

### Phase 3 — Radiology Module (Week 2)
*VistA Reference: Clinical Procedures / Imaging module*

**Data Model:**
```
royan_radiology_orders:
  id, encounter_id, patient_id, modality (xray|us|ct|mri|ecg|echo),
  body_part, clinical_indication, urgency (routine|urgent|stat),
  ordered_by, ordered_at, status (ordered|scheduled|in_progress|reported|cancelled),
  scheduled_at, radiologist_id, report, impression, tat_minutes,
  pacs_study_uid (nullable)
```

**Backend Endpoints — new router `radiology.py`:**
```
POST   /radiology/orders               — create imaging request
GET    /radiology/orders               — worklist (filter: status, modality, date)
GET    /radiology/orders/{id}          — get single order
PATCH  /radiology/orders/{id}/report   — radiologist submits report + impression
PATCH  /radiology/orders/{id}/status   — advance status
GET    /radiology/patients/{patient_id}/history — cumulative imaging history
GET    /radiology/stats                — TAT report, modality volume
```

**Frontend — new page `Radiology.tsx`:**
- Worklist table (filter by modality, status, date)
- "New Request" dialog (modality picker, body part, indication, urgency)
- Report entry dialog (radiologist impression + structured report)
- TAT KPI cards (average TAT per modality)
- AlertBanner at top

---

### Phase 4 — Surgical Theatre Module (Week 2-3)
*VistA Reference: Operating Room (OR) Management module*

**Data Model:**
```
royan_theatre_cases:
  id, encounter_id, patient_id, theatre_name, procedure_name,
  scheduled_date, start_time, end_time, surgeon_id, anaesthetist_id,
  status (scheduled|pre_op|in_theatre|recovery|completed|cancelled),
  urgency (elective|urgent|emergency), case_type,
  pre_op_checklist (JSONB), anaesthetic_record (JSONB),
  operative_notes, post_op_notes, scrub_nurse, circulating_nurse
```

**Backend Endpoints — new router `theatre.py`:**
```
POST   /theatre/cases                      — schedule theatre case
GET    /theatre/cases                      — theatre list (date, status, surgeon)
GET    /theatre/cases/{id}                 — case detail
PATCH  /theatre/cases/{id}/pre-op          — submit pre-op checklist
PATCH  /theatre/cases/{id}/anaesthetic     — anaesthetic record
PATCH  /theatre/cases/{id}/operative-notes — intraop notes
PATCH  /theatre/cases/{id}/post-op         — post-op recovery
PATCH  /theatre/cases/{id}/status          — advance status
GET    /theatre/schedule?date=X            — daily theatre schedule
```

**Frontend — new page `SurgicalTheatre.tsx`:**
- Daily schedule board (time slots per theatre)
- Case booking form
- Pre-op checklist stepper
- Anaesthetic record form
- Operative notes rich-text entry
- Post-op recovery monitoring

---

### Phase 5 — MCH / OB-GYN Module (Week 3)
*VistA Reference: Women's Health module*

**Data Model:**
```
royan_anc_records:
  id, patient_id, edd, lmp, gravida, para, booking_date, high_risk (bool),
  risk_factors (JSONB)

royan_anc_visits:
  id, anc_record_id, patient_id, visit_date, gestation_weeks,
  weight, bp, fundal_height, foetal_heart_rate, urine_protein,
  urine_glucose, oedema, presentation, notes, counselling_done

royan_partograph:
  id, patient_id, encounter_id, start_time,
  cervix_readings (JSONB array), foetal_heart_readings (JSONB array),
  contraction_readings (JSONB array), descent_readings (JSONB array),
  oxytocin_given, membrane_rupture_time, outcome

royan_delivery_records:
  id, patient_id, encounter_id, delivery_date, delivery_type,
  birth_weight, apgar_1, apgar_5, sex, complications,
  delivered_by, notes

royan_newborn_assessment:
  id, delivery_record_id, patient_id, birth_weight, head_circumference,
  length, resuscitation_needed, abnormalities, vitamin_k, hep_b_given

royan_immunisation:
  id, patient_id, vaccine, dose, date_given, given_by, next_due
```

**Backend Endpoints — new router `mchoygyn.py`:**
```
POST/GET /mch/anc/{patient_id}             — ANC registration + record
POST/GET /mch/anc/{record_id}/visits       — ANC visits
POST/GET /mch/partograph/{encounter_id}    — partograph (live update)
POST/GET /mch/delivery/{encounter_id}      — delivery record
POST/GET /mch/newborn/{delivery_id}        — newborn assessment
GET/POST /mch/immunisation/{patient_id}    — immunisation schedule
```

**Frontend — new page `MCHOBGyn.tsx`:**
- ANC booking + visit tracking table
- Partograph real-time chart (cervicogram + action line)
- Delivery record form
- Newborn assessment form
- Immunisation tracker with next-due alerts

---

### Phase 6 — SMS + Digital Engagement (Week 3)
*VistA Reference: Scheduling + Patient Communication*

| # | Feature | Provider | Implementation |
|---|---|---|---|
| 6.1 | SMS appointment reminders | Africa's Talking or Twilio | Background job fires at booking + 24h before; `POST /notifications/sms` internal endpoint |
| 6.2 | WhatsApp notifications | Twilio WhatsApp API or Meta BSP | Template messages: appointment confirm, result ready, bill summary |
| 6.3 | Patient portal (PWA) | React PWA | Separate build: view appointments, view results, pay bill via Paystack |
| 6.4 | Telemedicine stub | Daily.co or Jitsi Meet embed | Generate meeting link, attach to appointment; video consult room |

---

### Phase 7 — Quality, Safety & HR (Week 3-4)

| # | Feature | VistA Ref | Backend | Frontend |
|---|---|---|---|---|
| 7.1 | Incident report / RCA | Clinical Reminders | `royan_incidents` table + `POST /quality/incidents` | Incident form + RCA follow-up |
| 7.2 | Infection control log | | `royan_infection_log` table | Infection case log page |
| 7.3 | HEFAMAA checklist | | `royan_compliance_checks` table | Checklist page under Quality |
| 7.4 | Staff shift scheduling | HR | `royan_staff_shifts` table + CRUD | Shift roster calendar under HR |
| 7.5 | Leave management | HR | `royan_leave_requests` table | Leave request + approval workflow |
| 7.6 | Payroll stub | HR | `royan_payroll_runs` table | Payroll run summary page |

---

### Phase 8 — Reporting + Integrations (Week 4)

| # | Feature | Details |
|---|---|---|
| 8.1 | NHIA/HMIS export | Generate CSV/Excel in NHIA format; endpoint `GET /reports/nhia-export?month=X&year=Y` |
| 8.2 | Disease burden report | Aggregate ICD-10 diagnoses by period; `GET /reports/disease-burden` |
| 8.3 | Paystack integration | `POST /payments/initiate` → Paystack API → callback → update bill status |
| 8.4 | Flutterwave integration | Same pattern as Paystack; switch via config flag |
| 8.5 | PACS integration stub | `pacs_study_uid` field on radiology orders; webhook receiver for PACS push notifications |
| 8.6 | QR kiosk check-in | Generate QR per patient (UUID link); `POST /queue/kiosk-checkin?token=X` auto-registers to queue |

---

## 4. Specialist Clinic Templates

14 specialties requested. VistA TIU module handles this via **document definition templates**.

**Implementation approach:**
```
royan_clinic_templates:
  id, specialty, template_name, fields (JSONB schema), default_order_sets (JSONB)
```

Templates for:
1. Cardiology — ECG findings, cardiac history, medication review
2. ENT — hearing test, tympanogram, rhinoscopy findings
3. Ophthalmology — visual acuity, fundoscopy, IOP
4. Dermatology — skin lesion description, SCORAD score
5. Orthopaedics — range of motion, X-ray correlation
6. Neurology — GCS, cranial nerves, power grading
7. Gastroenterology — endoscopy findings, LFT interpretation
8. Urology — PSA, urodynamics
9. Pulmonology — spirometry, peak flow
10. Endocrinology — HbA1c trending, thyroid panel
11. Psychiatry — MSE (Mental State Exam), PHQ-9, GAD-7
12. Paediatrics — growth charts (WHO), developmental milestones
13. Oncology — staging, chemotherapy protocol
14. Dentistry — dental chart, periodontal scoring

---

## 5. Technical Architecture Notes

### 5.1 On-Premise Deployment Consideration
- The client requested **on-premise server** — this means:
  - FastAPI + Supabase should support **local Postgres instance** (Docker) or direct PostgreSQL
  - SMS/WhatsApp requires internet-out connectivity only (no inbound firewall)
  - Patient portal can be hosted on same server (Nginx reverse proxy)
  - Backups must be automated (pg_dump daily cron)

### 5.2 BCMA / Medication Safety Pattern (VistA)
VistA's BCMA module enforces 5 Rights at every dispense:
1. Right Patient
2. Right Medication
3. Right Dose
4. Right Route
5. Right Time

Synbot implementation:
- Allergy check → query `royan_allergies` before dispense confirmation
- DDI check → query `royan_drug_interactions` for active concurrent medications
- MAR verification → dispense creates a MAR entry
- Override with reason → required for any alert bypass (saved to audit)

### 5.3 VistA Longitudinal Patient Record
Patient Profile must be a **command center** (vista-4.md pattern):
```
LEFT: Sticky summary (demographics, HMO, allergies, active problems)
CENTER: Timeline (encounters → orders → results → notes)
RIGHT: Quick actions (new order, new note, add to queue)
```
Currently PatientProfile shows basic data — needs timeline view with all encounter history.

### 5.4 Audit-First Design
Every write operation must call `audit_event()` with:
- actor_id (JWT sub)
- subject_type + subject_id
- action + payload summary
This is already implemented for encounters, billing, prescriptions. Must extend to all new modules.

### 5.5 State Machine Pattern (already established)
New modules should follow the encounter state machine pattern:
```python
THEATRE_STATUS_TRANSITIONS = {
    "scheduled": {"pre_op", "cancelled"},
    "pre_op": {"in_theatre", "cancelled"},
    "in_theatre": {"recovery"},
    "recovery": {"completed"},
    "completed": set(),
    "cancelled": set(),
}
```

---

## 6. Database Tables Summary (New)

| Table | Module | Purpose |
|---|---|---|
| `royan_consent_records` | Registration | Patient consent capture per encounter |
| `royan_icd10_codes` | Clinical Doc | ICD-10 lookup reference |
| `royan_problem_list` | Clinical Doc | Active/inactive/resolved problems per patient |
| `royan_clinic_templates` | Specialist Clinics | Specialty-specific note templates |
| `royan_lab_reference_ranges` | Lab | Normal/critical ranges per test |
| `royan_drug_inventory` | Pharmacy | Stock levels per drug |
| `royan_drug_interactions` | Pharmacy (BCMA) | DDI pairs lookup |
| `royan_allergies` | BCMA | Patient allergy records |
| `royan_vitals` | Nursing | Vitals recordings per encounter |
| `royan_nursing_care_plans` | Nursing | Care plan entries |
| `royan_fluid_balance` | Nursing | Intake/output per shift |
| `royan_radiology_orders` | Radiology | Imaging requests + reports |
| `royan_theatre_cases` | Theatre | Surgical case scheduling + records |
| `royan_anc_records` | MCH | ANC patient booking |
| `royan_anc_visits` | MCH | ANC visit recordings |
| `royan_partograph` | MCH | Labour progress chart |
| `royan_delivery_records` | MCH | Delivery outcomes |
| `royan_newborn_assessment` | MCH | Newborn checks |
| `royan_immunisation` | MCH | Vaccination schedule/history |
| `royan_incidents` | Quality | Incident/adverse event reports |
| `royan_infection_log` | Quality | Infection control cases |
| `royan_compliance_checks` | Quality | HEFAMAA/regulatory checklists |
| `royan_staff_shifts` | HR | Shift scheduling |
| `royan_leave_requests` | HR | Leave requests + approvals |
| `royan_payroll_runs` | HR | Payroll period summaries |
| `royan_inpatient_bill_lines` | Billing | Per-service charge lines per admission |
| `royan_fee_schedule` | Billing | Service pricing rules |
| `royan_notifications_log` | Engagement | SMS/WhatsApp send log |

---

## 7. New Frontend Pages

| Page | Route | Module |
|---|---|---|
| `Radiology.tsx` | `/hospital/radiology` | Radiology |
| `SurgicalTheatre.tsx` | `/hospital/theatre` | Theatre |
| `MCHOBGyn.tsx` | `/hospital/mch` | MCH/OB-GYN |
| `NursingStation.tsx` | `/hospital/nursing` | Nursing |
| `ProblemList.tsx` | embedded in PatientProfile | Clinical Doc |
| `ConsentCapture.tsx` | embedded in PatientProfile | Registration |
| `SpecialistTemplate.tsx` | embedded in ClinicalQueue | Specialist Clinics |
| `DrugInventory.tsx` | `/hospital/pharmacy/inventory` | Pharmacy |
| `FeeSchedule.tsx` | `/admin/fee-schedule` | Billing |
| `AuditLog.tsx` | `/admin/audit-log` | Medical Records |
| `IncidentReport.tsx` | `/quality/incidents` | Quality |
| `StaffSchedule.tsx` | `/hr/schedule` | HR |
| `PatientPortal.tsx` | separate PWA build | Digital Engagement |
| `ReportsExport.tsx` | `/reports/export` | Reporting |

---

## 8. Implementation Priority Order

Given the client's ASAP (1-month) timeline, the sequence below balances clinical safety vs. delivery speed:

```
Week 1:  Phase 1 (Foundation Hardening) + Phase 2 (Lab/Pharmacy/Nursing)
Week 2:  Phase 3 (Radiology) + Phase 4 (Theatre)
Week 3:  Phase 5 (MCH/OB-GYN) + Phase 6 (SMS/Digital)
Week 4:  Phase 7 (Quality/HR) + Phase 8 (Reporting/Integrations) + QA + Deploy
```

**Critical path items** (must not slip):
1. Vitals recording — nursing cannot function without it
2. MAR (Medication Administration Record) — patient safety
3. DDI + Allergy checking — patient safety
4. Radiology worklist — radiology dept blocked without it
5. Theatre scheduling — surgical team blocked without it
6. ICD-10 + Problem list — NHIA reporting requires coded diagnoses

---

## 9. Next Action

Begin with **Phase 1** — it closes the most pressing gaps in already-live modules before introducing entirely new modules. The duplicate detection and ICD-10 features in particular will be needed from Day 1 of go-live.
