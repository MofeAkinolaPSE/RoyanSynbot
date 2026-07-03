ere's the complete breakdown of every column across all 6 entities:

Patients (60,927 records)
Column	Type	Populated From Hope
mrn	text	patient_id, mrn, file_no, hospital_no
first_name	text	full_name (split), first_name, fname
last_name	text	full_name (split), last_name, surname
date_of_birth	date	date_of_birth, dob, birth_date
gender	text	gender, sex
phone	text	phone, mobile, telephone
email	text	email
address	text	address
next_of_kin_name	text	next_of_kin, emergency_contact, guardian
next_of_kin_phone	text	nok_phone, emergency_phone
blood_group	text	blood_group, blood_type
genotype	text	genotype
allergies	text[]	allergies, allergy
hmo_provider	text	hmo, insurance_name, hmo_name
hmo_id	text	membership_no, policy_no
registered_at	timestamp	registration_date, reg_date
external_id	text	Hope patient ID (for sync tracking)
Appointments (253,401 records)
Column	Type	Populated From Hope
patient_id	FK → patients	matched via Hope patient_id
doctor_name	text	doctor, physician, consultant
department	text	department, dept, clinic
slot_date	date	appointment_date, visit_date
slot_time	time	appointment_time, start_time
reason	text	reason_for_visit, complaint, purpose
status	text	status, appt_status
external_id	text	appointment_id, appt_id
Admissions / Encounters (256,452 records)
Column	Type	Populated From Hope
patient_id	FK → patients	matched via Hope patient_id
encounter_type	text	outpatient / inpatient / emergency
chief_complaint	text	complaints, presenting_complaint
consulting_doctor	text	consultant, doctor_name, physician
diagnosis_notes	text	diagnosis, icd_code, final_diagnosis
triage_level	text	triage, triage_score
department	text	department, dept
discharge_at	timestamp	discharge_date, date_discharged
discharge_summary	text	discharge_notes
external_id	text	admission_id
Lab Orders (203,521 records)
Column	Type	Populated From Hope
patient_id	FK → patients	matched via Hope patient_id
test_name	text	test_name, investigation, description, service_name, item_name
test_code	text	laboratory_id, test_code
urgency	text	urgency, priority
status	text	labdash_status, lab_status
ordered_by	text	doctor_id, requesting_doctor
ordered_at	timestamp	lab_order_date, request_date
sample_type	text	specimen, specimen_type
notes	text	result_summary, findings, comments
external_id	text	lab_id, order_id, request_id
Prescriptions (258,618 records)
Column	Type	Populated From Hope
patient_id	FK → patients	matched via Hope patient_id
drug_name	text	drug_name, medication, item_name, product_name
drug_code	text	nafdac_no, drug_id
dosage	text	dosage, dose, strength
frequency	text	frequency, dosage_frequency
duration	text	duration, days
route	text	route, route_of_admin (oral/iv/im etc.)
quantity	numeric	quantity, qty_dispensed
unit	text	unit_of_measure, form
prescribed_by	text	doctor, prescriber
prescribed_at	timestamp	order_date, created_at
status	text	pending / dispensed / cancelled
external_id	text	prescription_id, dispense_id
Billing (251,986 records)
Column	Type	Populated From Hope
patient_id	FK → patients	matched via Hope patient_id
bill_number	text	bill_number, bill_code
consultation_fee	numeric	broken out from total_amount
lab_charges	numeric	broken out from total_amount
pharmacy_charges	numeric	broken out from total_amount
ward_charges	numeric	broken out from total_amount
hmo_covered	numeric	hmo_amount, insurance_amount
subtotal	numeric (computed)	auto-calculated
patient_balance	numeric (computed)	subtotal − discount − hmo_covered
status	text	pending / partial / paid / waived
payment_method	text	cash / card / transfer / hmo
billed_at	timestamp	invoice_date, bill_date
external_id	text	invoice_id, bill_id, transaction_id