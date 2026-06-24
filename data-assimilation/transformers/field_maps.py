"""Field mapping configuration for DRM Hope → RoyanHealth schema.

Each dict maps a DRM Hope column name (lowercase) to a RoyanHealth field name.
Special values:
  "__split__"          — split the value on the first space into first_name / last_name
  "__patient_lookup__" — look up the RoyanHealth patient_id from this Hope patient_id

TABLE_HINTS tells the pipeline which raw table name(s) to look for in the dump
for each logical entity.  The first match wins.

IMPORTANT: After running  python ingest.py --source dump --file ... --step discover
paste the output to Claude and the actual column names will be filled in here
before the real load.
"""

# ---------------------------------------------------------------------------
# Table name hints (tried in order — first match wins)
# ---------------------------------------------------------------------------
TABLE_HINTS: dict = {
    # Actual Hope table names are listed first; generic guesses follow as fallback.
    # Hope: `patients` has admission context, `persons` has demographics.
    # Pipeline tries patients first (has the clinical context + lookup_name).
    # persons is a fallback with split first/last name.
    "patients":          ["patients", "persons", "patient", "tbl_patients", "drm_patients", "patient_master"],
    "appointments":      ["appointments", "appointment", "tbl_appointments", "opd_appointments", "opd_schedule"],
    # Hope stores encounters/clinical notes in `diagnoses`; older dumps use `admissions`
    "admissions":        ["diagnoses", "encounters", "admissions", "admission", "inpatient",
                          "inpatient_admissions", "tbl_admissions", "ward_admissions"],
    # Lab orders may be embedded in diagnoses.investigation (older Hope) or separate table
    "lab":               ["laboratory_test_orders", "lab_test_orders", "lab_orders", "lab_order",
                          "laboratory_orders", "tbl_lab", "lab_requests", "investigations"],
    # Hope stores prescriptions in `diagnosis_drugs`; newer versions have separate pharmacy_sales_bills
    "pharmacy":          ["diagnosis_drugs", "pharmacy_sales_bills", "prescriptions", "prescription",
                          "pharmacy", "dispensing", "tbl_dispensing", "drug_orders", "pharmacy_orders"],
    # Hope billing lives in service_bills and consultant_billings
    "billing":           ["service_bills", "consultant_billings", "billing", "invoices", "invoice",
                          "tbl_billing", "bills", "transactions"],
    # Hope stores HMO/insurance providers in `insurance_companies`
    "hmo":               ["insurance_companies", "hmo", "hmo_providers", "insurance_providers",
                          "tbl_hmo", "insurers"],
    "patient_insurance": ["patient_insurance", "patient_hmo", "insurance_enrollments", "member_insurance"],
    "radiology":         ["radiology_test_orders", "radiology_orders", "xray_orders", "imaging_orders",
                          "radiology_requests", "xray", "imaging", "tbl_radiology", "scan_requests",
                          "radiology"],
    "theatre":           ["theatre_records", "theatre_cases", "surgical_records", "operations",
                          "surgical_cases", "tbl_theatre", "operating_theatre"],
    "operations":        ["fumigation_records", "fumigation", "maintenance_records", "maintenance",
                          "deviations", "deviation_log", "audit_records", "compliance_log", "recall_events"],
    "hmo_plans":         ["hmo_plans", "insurance_plans", "tbl_hmo_plans", "hmo_packages"],
    # Staff / consultants
    "staff":             ["consultants", "doctors", "staff", "tbl_staff", "users", "employees"],
    # Wards
    "wards":             ["wards", "ward", "tbl_wards", "ward_master"],
}

# ---------------------------------------------------------------------------
# Field maps (DRM Hope column → RoyanHealth field)
# ---------------------------------------------------------------------------

PATIENT_MAP: dict = {
    # Hope `patients` table: `id` = DB pk, `patient_id` = external MRN (e.g. 'RH16-27')
    "id":             "external_id",
    "patientid":      "external_id",

    # `patient_id` in Hope is the *human-readable* patient number (MRN), not the DB pk
    "patient_id":     "mrn",

    # Name — Hope `patients.full_name` is often empty; actual name is in `lookup_name`
    # Fall back chain: lookup_name → full_name → first_name+last_name
    "lookup_name":    "__split__",    # confirmed actual data source (e.g. 'Henry Nj Warner')
    "full_name":      "__split__",
    "fullname":       "__split__",
    "patient_name":   "__split__",
    # If Hope stores split first/last (persons table shape):
    "first_name":     "first_name",
    "firstname":      "first_name",
    "fname":          "first_name",
    "last_name":      "last_name",
    "lastname":       "last_name",
    "lname":          "last_name",
    "surname":        "last_name",
    "name":           "__split__",

    # Demographics
    "date_of_birth":  "date_of_birth",
    "dob":            "date_of_birth",
    "birth_date":     "date_of_birth",
    "birthday":       "date_of_birth",
    "gender":         "gender",
    "sex":            "gender",

    # Contact
    "phone":          "phone",
    "phone_number":   "phone",
    "mobile":         "phone",
    "mobile_number":  "phone",
    "mobile_phone":   "phone",      # actual Hope column name
    "landline_phone": "phone",
    "telephone":      "phone",
    "phone_no":       "phone",
    "email":          "email",
    "address":        "address",
    "address1":       "address",    # actual Hope column name

    # Clinical
    "blood_group":    "blood_group",
    "bloodgroup":     "blood_group",
    "blood_type":     "blood_group",
    "genotype":       "genotype",
    "allergies":      "allergies",
    "allergy":        "allergies",

    # Next of kin / emergency contact
    "next_of_kin":          "next_of_kin_name",
    "next_of_kin_name":     "next_of_kin_name",
    "nok_name":             "next_of_kin_name",
    "kin_name":             "next_of_kin_name",
    "emergency_contact":    "next_of_kin_name",
    "guardian":             "next_of_kin_name",
    "next_of_kin_phone":    "next_of_kin_phone",
    "nok_phone":            "next_of_kin_phone",
    "kin_phone":            "next_of_kin_phone",
    "emergency_phone":      "next_of_kin_phone",
    "nok_mobile":           "next_of_kin_phone",

    # HMO / Insurance
    "hmo":                   "hmo_provider",
    "hmo_provider":          "hmo_provider",
    "insurance":             "hmo_provider",
    "insurance_name":        "hmo_provider",
    "hmo_name":              "hmo_provider",
    "hmo_id":                "hmo_id",
    "membership_no":         "hmo_id",
    "member_no":             "hmo_id",
    "membership_id":         "hmo_id",
    "policy_no":             "hmo_id",
    # actual Hope FK to insurance_companies table
    "insurance_company_id":  "_hope_hmo_id",

    # Record number (Hope `patient_id` col already mapped to mrn above)
    "mrn":            "mrn",
    "mrn_number":     "mrn",
    "patient_uid":    "mrn",         # persons table: 'RH16-1' format
    "medical_record_no": "mrn",
    "hospital_no":    "mrn",
    "file_no":        "mrn",
    "patient_no":     "mrn",
    "admission_id":   "mrn",         # Hope 'RO/I-01' admission reference

    # Timestamps
    "created_at":        "registered_at",
    "registration_date": "registered_at",
    "reg_date":          "registered_at",
    "create_time":       "registered_at",   # actual Hope column name
    "updated_at":        "external_updated_at",
    "modify_time":       "external_updated_at",  # actual Hope column name
}

APPOINTMENT_MAP: dict = {
    "appointment_id":   "external_id",
    "id":               "external_id",
    "appt_id":          "external_id",

    "patient_id":       "__patient_lookup__",
    "patientid":        "__patient_lookup__",

    "doctor":           "doctor_name",
    "doctor_name":      "doctor_name",
    "physician":        "doctor_name",
    "consultant":       "doctor_name",
    "doctor_id":        "doctor_name",  # will store the id as name if no name available

    "department":       "department",
    "department_id":    "department",   # actual Hope FK (store id as label; resolved later)
    "dept":             "department",
    "clinic":           "department",

    "appointment_date": "slot_date",
    "appt_date":        "slot_date",
    "visit_date":       "slot_date",
    "date":             "slot_date",
    "schedule_date":    "slot_date",

    "appointment_time": "slot_time",
    "appt_time":        "slot_time",
    "start_time":       "slot_time",    # actual Hope column name
    "time":             "slot_time",
    "schedule_time":    "slot_time",

    "status":           "status",
    "appt_status":      "status",

    "reason":           "reason",
    "reason_for_visit": "reason",
    "complaint":        "reason",
    "purpose":          "reason",       # actual Hope column name
    "visit_type":       "reason",       # actual Hope column name

    "created_at":       "external_updated_at",
    "updated_at":       "external_updated_at",
    "create_time":      "external_updated_at",  # actual Hope column name
}

ADMISSION_MAP: dict = {
    # Primary key
    "admission_id":   "external_id",
    "id":             "external_id",
    "admit_id":       "external_id",

    "patient_id":     "__patient_lookup__",
    "patientid":      "__patient_lookup__",

    # Ward / bed (inpatient) — stored as private strings; loader resolves to FK integers
    "ward":           "_ward_name",
    "ward_name":      "_ward_name",
    "ward_id":        "_ward_name",
    "bed":            "_bed_label",
    "bed_no":         "_bed_label",
    "bed_number":     "_bed_label",
    "bed_id":         "_bed_label",

    # Admission / discharge dates (inpatient)
    "admitted_at":    "admitted_at",
    "admission_date": "admitted_at",
    "admit_date":     "admitted_at",
    "date_admitted":  "admitted_at",
    "discharged_at":  "discharged_at",
    "discharge_date": "discharged_at",
    "date_discharged":"discharged_at",

    # Clinical notes — actual Hope `diagnoses` table column names
    "complaints":             "chief_complaint",   # chief complaint field
    "presenting_complaint":   "chief_complaint",
    "diagnosis":              "diagnosis_notes",
    "diagnosis_notes":        "diagnosis_notes",
    "final_diagnosis":        "diagnosis_notes",   # actual Hope column
    "primary_diagnosis":      "diagnosis_notes",
    "icd_code":               "icd_code",          # ICD-10 code field
    "icd10_code":             "icd_code",
    "icd10":                  "icd_code",
    # diagnoses.investigation holds embedded JSON for lab/radiology requests
    "investigation":          "_hope_investigation_json",

    # Triage data
    "triage_level":       "triage_level",
    "triage":             "triage_level",
    "triage_score":       "triage_level",
    "triage_category":    "triage_level",
    "triage_notes":       "triage_notes",
    "triage_complaint":   "triage_notes",
    "triage_at":          "triage_at",
    "triage_time":        "triage_at",
    "triage_date":        "triage_at",
    "triage_by":          "triage_by",
    "triaged_by":         "triage_by",
    "triage_nurse":       "triage_by",

    # Discharge details
    "discharge_summary":  "discharge_summary",
    "discharge_notes":    "discharge_summary",
    "discharge_by":       "discharge_by",
    "discharged_by":      "discharge_by",

    # Consulting doctor — actual Hope `diagnoses` table column names
    "consultant":         "consulting_doctor",
    "consultant_sb":      "consulting_doctor",     # actual Hope column (staff id)
    "doctor":             "consulting_doctor",
    "doctor_name":        "consulting_doctor",
    "physician":          "consulting_doctor",
    "attending_doctor":   "consulting_doctor",

    # Registered by (reception staff)
    "register_sb":        "registered_by",         # actual Hope column (staff id)
    "registered_by":      "registered_by",

    # Consultation timestamp
    "consultant_on":      "consultation_at",       # actual Hope column (datetime)

    # Timestamps
    "created_at":         "external_updated_at",
    "updated_at":         "external_updated_at",
    "create_time":        "external_updated_at",   # actual Hope column name
    "modify_time":        "external_updated_at",
}

LAB_MAP: dict = {
    # Hope `laboratory_test_orders` actual columns (confirmed from discover)
    "id":                 "external_id",
    "lab_id":             "external_id",
    "order_id":           "external_id",   # actual: 'Lab16-1' format
    "lab_order_id":       "external_id",
    "request_id":         "external_id",

    "patient_id":         "__patient_lookup__",
    "patientid":          "__patient_lookup__",

    # Test identity — laboratory_id is FK to `laboratories` (test catalog)
    "laboratory_id":      "test_code",     # store the lab catalog FK as test_code
    "test_name":          "test_name",
    "test_type":          "test_name",
    "test":               "test_name",
    "investigation":      "test_name",
    "lab_test":           "test_name",
    "description":        "test_name",     # some Hope versions use description for test name
    "service_name":       "test_name",     # pharmacy_sales_bills style lab items
    "item_name":          "test_name",     # fallback item label
    "test_code":          "test_code",

    "urgency":            "urgency",
    "priority":           "urgency",

    # Status — actual column: `labdash_status` (e.g. 'Pending', 'Completed')
    "labdash_status":     "status",
    "status":             "status",
    "lab_status":         "status",

    "sample_type":        "sample_type",
    "specimen":           "sample_type",
    "specimen_type":      "sample_type",
    "specimen_type_option": "sample_type", # actual Hope column

    # Timestamp — actual column: `start_date` or `lab_order_date`
    "start_date":         "ordered_at",    # actual Hope column
    "lab_order_date":     "ordered_at",    # actual Hope column
    "ordered_at":         "ordered_at",
    "order_date":         "ordered_at",
    "request_date":       "ordered_at",
    "created_at":         "ordered_at",
    "create_time":        "ordered_at",

    "resulted_at":        "external_updated_at",
    "result_date":        "external_updated_at",
    "updated_at":         "external_updated_at",
    "modify_time":        "external_updated_at",

    "result_summary":     "notes",
    "result":             "notes",
    "findings":           "notes",
    "comments":           "notes",
    "relevant_clinical_info": "notes",     # actual Hope column

    # Doctor
    "doctor_id":          "ordered_by",    # actual Hope column (FK)
    "ordered_by":         "ordered_by",
    "doctor":             "ordered_by",
    "requesting_doctor":  "ordered_by",
    "user_id":            "ordered_by",    # fallback if no doctor_id
}

PHARMACY_MAP: dict = {
    "order_id":        "external_id",
    "prescription_id": "external_id",
    "dispense_id":     "external_id",
    "id":              "external_id",

    "patient_id":      "__patient_lookup__",
    "patientid":       "__patient_lookup__",

    "drug_name":       "drug_name",
    "drug":            "drug_name",
    "medication":      "drug_name",
    "item_name":       "drug_name",
    "product_name":    "drug_name",

    "drug_code":       "drug_code",
    "nafdac_no":       "drug_code",
    "drug_id":         "drug_code",

    "dosage":          "dosage",
    "dose":            "dosage",
    "strength":        "dosage",

    "frequency":       "frequency",
    "dosage_frequency":"frequency",

    "duration":        "duration",
    "days":            "duration",

    "route":           "route",
    "route_of_admin":  "route",

    "quantity":        "quantity",
    "qty":             "quantity",
    "qty_dispensed":   "quantity",

    "unit":            "unit",
    "unit_of_measure": "unit",
    "form":            "unit",

    "status":          "status",

    "instructions":    "special_instructions",
    "special_instructions": "special_instructions",

    "prescribed_by":   "prescribed_by",
    "doctor":          "prescribed_by",
    "prescriber":      "prescribed_by",

    "prescribed_at":   "prescribed_at",
    "ordered_at":      "prescribed_at",
    "order_date":      "prescribed_at",
    "created_at":      "prescribed_at",
    "create_time":     "prescribed_at",     # actual Hope column name

    "updated_at":      "external_updated_at",
    "modify_time":     "external_updated_at",

    # diagnosis_drugs specific columns (actual Hope prescription table)
    "diagnosis_id":    "_hope_encounter_id", # FK to diagnoses table
    "mode":            "route",              # administration route in Hope
    "tabs_per_day":    "dosage",             # e.g. "2" tablets per day
    "tabs_frequency":  "frequency",          # e.g. "morning" / "twice daily"
    "drug_id":         "drug_code",          # FK to drugs table
}

BILLING_MAP: dict = {
    "invoice_id":      "external_id",
    "bill_id":         "external_id",
    "id":              "external_id",
    "transaction_id":  "external_id",

    "patient_id":      "__patient_lookup__",
    "patientid":       "__patient_lookup__",

    # Amount — confirmed actual columns from Hope `billings` and `service_bills`
    # All mapped to raw_amount; routed to the right fee column by billing.py
    "total_amount":         "raw_amount",  # billings.total_amount (confirmed)
    "amount":               "raw_amount",  # service_bills.amount / billings.amount
    "total":                "raw_amount",  # pharmacy_sales_bills.total
    "gross_amount":         "raw_amount",
    "bill_amount":          "raw_amount",
    "amount_net_covered":   "raw_amount",  # actual Hope column

    # Category hint — billings uses `payment_category` (FK, stored as hint)
    "category":             "category_hint",
    "payment_category":     "category_hint",  # actual Hope billings column (FK id)
    "service_type":         "category_hint",
    "item_type":            "category_hint",
    "charge_type":          "category_hint",
    "department":           "category_hint",

    # Bill reference number
    "bill_number":          "bill_number",   # actual Hope column: 'BL16-J17/1'
    "bill_code":            "bill_number",   # pharmacy_sales_bills column: 'SB-0001'

    "hmo_claim":       "hmo_covered",
    "hmo_amount":      "hmo_covered",
    "insurance_amount":"hmo_covered",
    "covered_amount":  "hmo_covered",

    "patient_due":     "patient_balance",
    "patient_amount":  "patient_balance",
    "copay":           "patient_balance",

    "discount":        "discount",

    "status":             "status",
    "payment_status":     "status",

    "payment_method":     "payment_method",
    "pay_method":         "payment_method",
    "mode_of_payment":    "payment_method",  # actual Hope billings column
    "payment_mode":       "payment_method",  # pharmacy_sales_bills column

    "invoice_date":    "billed_at",
    "bill_date":       "billed_at",
    "created_at":      "billed_at",
    "date":            "billed_at",         # actual Hope service_bills column
    "create_time":     "billed_at",         # actual Hope column name

    "updated_at":      "external_updated_at",
    "paid_at":         "external_updated_at",
    "modify_time":     "external_updated_at",

    "notes":           "notes",
    "remarks":         "notes",

    # service_bills specific columns
    "service_id":      "service_id",        # FK to services/tariff table
    "service_charge":  "raw_amount",        # service tariff amount
    "charge":          "raw_amount",
    # consultant_billings specific columns
    "consultant_id":   "staff_id",          # FK to consultants
    "morning":         "raw_amount",        # ward billing by shift (service_bills)
    "evening":         "raw_amount",
    "night":           "raw_amount",
}

HMO_MAP: dict = {
    "hmo_id":          "external_id",
    "id":              "external_id",

    "hmo_name":        "name",
    "name":            "name",
    "provider_name":   "name",
    "insurance_name":  "name",

    "code":            "code",
    "hmo_code":        "code",
    "provider_code":   "code",

    "phone":           "contact_phone",
    "phone_number":    "contact_phone",
    "contact_phone":   "contact_phone",

    "email":           "contact_email",
    "contact_email":   "contact_email",

    "is_active":       "is_active",
    "active":          "is_active",
    "status":          "is_active",
}

# ---------------------------------------------------------------------------
# Radiology / Imaging field map
# ---------------------------------------------------------------------------
RADIOLOGY_MAP: dict = {
    "radiology_id":     "external_id",
    "xray_id":          "external_id",
    "imaging_id":       "external_id",
    "scan_id":          "external_id",
    "request_id":       "external_id",
    "id":               "external_id",

    "patient_id":       "__patient_lookup__",
    "patientid":        "__patient_lookup__",

    # Actual Hope `radiology_test_orders` columns (confirmed from discover)
    "radiology_id":      "test_code",      # FK to radiology catalog
    "order_id":          "external_id",    # 'RADRRO116J17001' format — overrides id above
    "testname":          "study_type",     # actual Hope column (e.g. 'CT SCAN EXTREMITY')
    "study_type":        "study_type",
    "modality":          "study_type",
    "type":              "study_type",
    "exam_type":         "study_type",

    "body_part":         "body_region",
    "body_region":       "body_region",
    "region":            "body_region",
    "anatomy":           "body_region",

    # Doctor
    "doctor_id":         "ordering_doctor",  # actual Hope column
    "requesting_doctor": "ordering_doctor",
    "doctor":            "ordering_doctor",
    "referred_by":       "ordering_doctor",
    "doctor_name":       "ordering_doctor",
    "primary_care_pro":  "ordering_doctor",  # actual Hope column ('FUNMI AKINOLA')

    "radiographer":     "radiographer",
    "technician":       "radiographer",
    "performed_by":     "radiographer",

    "status":           "status",

    "report":           "report_text",
    "findings":         "report_text",
    "impression":       "report_text",
    "result":           "report_text",

    "performed_at":          "performed_at",
    "exam_date":             "performed_at",
    "scan_date":             "performed_at",
    "radiology_order_date":  "performed_at",  # actual Hope column

    "reported_at":      "reported_at",
    "report_date":      "reported_at",
    "result_date":      "reported_at",

    "created_at":       "external_updated_at",
    "updated_at":       "external_updated_at",
    "create_time":      "external_updated_at",
    "modify_time":      "external_updated_at",

    # Clinical context
    "relevant_clinical_info": "report_text",  # actual Hope column
    "additional_notes":       "report_text",  # actual Hope column
    "related_diagnosis":      "report_text",  # PHP serialized, store raw
    "diagnosis":              "report_text",
    "findings":               "report_text",
}

# ---------------------------------------------------------------------------
# Theatre / Surgical field map
# ---------------------------------------------------------------------------
THEATRE_MAP: dict = {
    "theatre_id":       "external_id",
    "operation_id":     "external_id",
    "surgical_id":      "external_id",
    "case_id":          "external_id",
    "id":               "external_id",

    "patient_id":       "__patient_lookup__",
    "patientid":        "__patient_lookup__",

    "procedure_name":   "procedure_name",
    "operation_name":   "procedure_name",
    "surgery_name":     "procedure_name",
    "procedure":        "procedure_name",

    "surgeon":          "surgeon",
    "lead_surgeon":     "surgeon",
    "operating_surgeon":"surgeon",
    "doctor":           "surgeon",

    "anaesthetist":     "anaesthetist",
    "anesthesiologist": "anaesthetist",
    "anaesthesia_by":   "anaesthetist",

    "scrub_nurse":      "scrub_nurse",
    "circulating_nurse":"scrub_nurse",

    "status":           "status",

    "theatre_room":     "theatre_room",
    "theatre_no":       "theatre_room",
    "operating_room":   "theatre_room",

    "scheduled_at":     "scheduled_at",
    "scheduled_date":   "scheduled_at",
    "operation_date":   "scheduled_at",

    "started_at":       "started_at",
    "start_time":       "started_at",
    "incision_time":    "started_at",

    "ended_at":         "ended_at",
    "end_time":         "ended_at",
    "closure_time":     "ended_at",

    "duration":         "duration_mins",
    "duration_mins":    "duration_mins",
    "duration_minutes": "duration_mins",

    "anaesthesia_type": "anaesthesia_type",
    "anaesthesia":      "anaesthesia_type",
    "anesthesia_type":  "anaesthesia_type",

    "notes":            "notes",
    "remarks":          "notes",
    "complications":    "notes",

    "created_at":       "external_updated_at",
    "updated_at":       "external_updated_at",
}

# ---------------------------------------------------------------------------
# Generic operations / events field map (fumigation, maintenance, deviation, etc.)
# ---------------------------------------------------------------------------
OPERATIONS_MAP: dict = {
    "id":               "external_id",
    "record_id":        "external_id",
    "event_id":         "external_id",
    "log_id":           "external_id",

    "date":             "event_date",
    "event_date":       "event_date",
    "occurrence_date":  "event_date",
    "report_date":      "event_date",
    "scheduled_date":   "event_date",

    "title":            "title",
    "description":      "title",
    "subject":          "title",
    "name":             "title",
    "task":             "title",

    "status":           "status",
    "completion_status":"status",

    "severity":         "severity",
    "priority":         "severity",
    "risk_level":       "severity",

    "performed_by":     "performed_by",
    "done_by":          "performed_by",
    "technician":       "performed_by",
    "officer":          "performed_by",
    "staff":            "performed_by",

    "department":       "department",
    "location":         "department",
    "area":             "department",

    "notes":            "notes",
    "remarks":          "notes",
    "comments":         "notes",
    "findings":         "notes",

    "created_at":       "external_updated_at",
    "updated_at":       "external_updated_at",
}

# ---------------------------------------------------------------------------
# HMO plan field map
# ---------------------------------------------------------------------------
HMO_PLAN_MAP: dict = {
    "plan_id":          "external_id",
    "id":               "external_id",

    "plan_name":        "name",
    "name":             "name",

    "plan_code":        "plan_code",
    "code":             "plan_code",

    "hmo_id":           "_hope_hmo_id",
    "provider_id":      "_hope_hmo_id",

    "is_active":        "is_active",
    "active":           "is_active",

    "notes":            "notes",
    "description":      "notes",
}

# ---------------------------------------------------------------------------
# Patient insurance enrollment field map
# ---------------------------------------------------------------------------
PATIENT_INSURANCE_MAP: dict = {
    "enrollment_id":    "external_id",
    "id":               "external_id",
    "record_id":        "external_id",

    "patient_id":       "__patient_lookup__",
    "patientid":        "__patient_lookup__",

    "hmo_id":           "_hope_hmo_id",
    "provider_id":      "_hope_hmo_id",
    "insurer_id":       "_hope_hmo_id",

    "membership_id":    "membership_id",
    "member_no":        "membership_id",
    "policy_no":        "membership_id",
    "card_no":          "membership_id",

    "status":           "status",
    "enrollment_status":"status",

    "valid_from":       "valid_from",
    "start_date":       "valid_from",
    "effective_date":   "valid_from",

    "valid_to":         "valid_to",
    "end_date":         "valid_to",
    "expiry_date":      "valid_to",

    "is_primary":       "is_primary",
    "primary":          "is_primary",
}

# ---------------------------------------------------------------------------
# Consultants / Staff field map  (Hope `consultants` table → royan_staff)
# ---------------------------------------------------------------------------
CONSULTANT_MAP: dict = {
    "id":               "external_id",
    "consultant_id":    "external_id",

    "first_name":       "first_name",
    "firstname":        "first_name",
    "fname":            "first_name",
    "last_name":        "last_name",
    "lastname":         "last_name",
    "surname":          "last_name",
    "full_name":        "__split__",

    "phone1":           "phone",
    "phone":            "phone",
    "mobile":           "phone",
    "mobile_phone":     "phone",

    "email":            "email",

    "specialty":        "department",
    "specialization":   "department",
    "department":       "department",

    "is_active":        "is_active",
    "active":           "is_active",

    "created_at":       "external_updated_at",
    "create_time":      "external_updated_at",
}

# ---------------------------------------------------------------------------
# Ward field map  (Hope `wards` table → royan_wards)
# ---------------------------------------------------------------------------
WARD_MAP: dict = {
    "id":           "external_id",
    "ward_id":      "external_id",
    "wardid":       "external_id",

    "name":         "ward_name",
    "ward_name":    "ward_name",

    "no_of_rooms":  "total_beds",
    "rooms":        "total_beds",
    "capacity":     "total_beds",

    "bed_prefix":   "bed_prefix",

    "is_active":    "is_active",
    "active":       "is_active",
}
