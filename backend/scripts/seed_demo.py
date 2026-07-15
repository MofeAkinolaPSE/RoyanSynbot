"""
Demo seed script for RoyanHealth — Royan Hospital
Populates realistic data for all 10 walkthrough demo scenes.

Run from repo root:
    docker exec royan_backend python scripts/seed_demo.py

Or locally (needs DATABASE_URL in env):
    python backend/scripts/seed_demo.py
"""

import os
import sys
import logging
import bcrypt
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:admin1234@localhost:5432/synbot_health"
)

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def connect():
    return psycopg2.connect(DATABASE_URL)


def seed_users(cur):
    log.info("→ Seeding demo user accounts...")
    users = [
        ("dr.adeyemi@royanhospital.com",   hash_pw("Demo1234!"), ["doctor"]),
        ("lab.tech@royanhospital.com",      hash_pw("Demo1234!"), ["lab_tech"]),
        ("pharmacist@royanhospital.com",    hash_pw("Demo1234!"), ["pharmacist"]),
        ("finance@royanhospital.com",       hash_pw("Demo1234!"), ["finance"]),
        ("receptionist@royanhospital.com",  hash_pw("Demo1234!"), ["receptionist"]),
        ("nurse@royanhospital.com",         hash_pw("Demo1234!"), ["nurse"]),
        ("ward.manager@royanhospital.com",  hash_pw("Demo1234!"), ["ward_manager"]),
    ]
    for email, hpw, roles in users:
        cur.execute("""
            INSERT INTO royan_users (email, hashed_password, roles)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET roles = EXCLUDED.roles
        """, (email, hpw, roles))
    log.info(f"   ✓ {len(users)} staff accounts ready  (password: Demo1234!)")


def seed_wards_and_beds(cur):
    log.info("→ Seeding wards and beds...")
    wards = [
        ("Ward A — General",   "general",   "1st Floor", 10),
        ("Ward B — General",   "general",   "1st Floor", 15),
        ("Ward C — Surgical",  "surgical",  "2nd Floor",  8),
        ("ICU",                "icu",        "Ground",     6),
        ("Maternity Ward",     "maternity", "2nd Floor",  8),
        ("Emergency Bay",      "emergency", "Ground",     5),
    ]
    ward_ids = {}
    for name, wtype, floor, total in wards:
        cur.execute("""
            INSERT INTO royan_wards (name, ward_type, floor, total_beds)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET total_beds = EXCLUDED.total_beds
            RETURNING id
        """, (name, wtype, floor, total))
        ward_ids[name] = cur.fetchone()[0]

    # Ward A beds (6 available, 4 occupied for demo realism)
    for i in range(1, 11):
        status = "occupied" if i <= 4 else "available"
        cur.execute("""
            INSERT INTO royan_beds (ward_id, bed_number, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (ward_id, bed_number) DO UPDATE SET status = EXCLUDED.status
        """, (ward_ids["Ward A — General"], f"A{i:02d}", status))

    # Ward B beds (13 occupied = 87% for Bed Capacity Agent demo trigger)
    for i in range(1, 16):
        status = "occupied" if i <= 13 else "available"
        cur.execute("""
            INSERT INTO royan_beds (ward_id, bed_number, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (ward_id, bed_number) DO UPDATE SET status = EXCLUDED.status
        """, (ward_ids["Ward B — General"], f"B{i:02d}", status))

    # Surgical / ICU / Emergency
    for ward, prefix, count in [
        ("Ward C — Surgical", "C", 8),
        ("Emergency Bay",     "E", 5),
    ]:
        for i in range(1, count + 1):
            cur.execute("""
                INSERT INTO royan_beds (ward_id, bed_number, status)
                VALUES (%s, %s, 'available')
                ON CONFLICT (ward_id, bed_number) DO NOTHING
            """, (ward_ids[ward], f"{prefix}{i:02d}"))

    log.info(f"   ✓ {len(wards)} wards, beds seeded (Ward B at 87% for agent demo)")
    return ward_ids


def seed_patients(cur):
    log.info("→ Seeding demo patients...")
    today = date.today()
    patients = [
        # (mrn, first, last, dob, gender, phone, blood, genotype, allergies, hmo_provider, hmo_id)
        ("RYN-00247", "Emeka",   "Okafor",  date(1978, 3, 15), "male",   "08031234567", "O+",  "AA", ["Penicillin"],          "AXA Mansard",  "AXA-0012345"),
        ("RYN-00248", "Halima",  "Bello",   date(1991, 8, 2),  "female", "08057891234", "A+",  "AS", [],                     None,           None),
        ("RYN-00249", "Chidi",   "Eze",     date(1965, 6, 20), "male",   "08021112233", "B+",  "AA", ["Sulphonamides"],       "NHIS",         "NHIS-7788991"),
        ("RYN-00250", "Amina",   "Yusuf",   date(1995, 11, 5), "female", "07011223344", "AB+", "AS", [],                     "Hygeia HMO",   "HYG-0044321"),
        ("RYN-00251", "Tunde",   "Adewale", date(1958, 4, 12), "male",   "08099887766", "O-",  "AA", ["Aspirin", "NSAIDs"],   "Leadway Assur","LWA-5521983"),
    ]
    patient_ids = {}
    for mrn, fn, ln, dob, gender, phone, bg, geno, allergies, hmo, hmo_id in patients:
        cur.execute("""
            INSERT INTO royan_patients
              (mrn, first_name, last_name, date_of_birth, gender, phone,
               blood_group, genotype, allergies, hmo_provider, hmo_id, registered_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'admin')
            ON CONFLICT (mrn) DO UPDATE SET
              hmo_provider = EXCLUDED.hmo_provider,
              hmo_id       = EXCLUDED.hmo_id
            RETURNING id
        """, (mrn, fn, ln, dob, gender, phone, bg, geno, allergies, hmo, hmo_id))
        patient_ids[mrn] = cur.fetchone()[0]

    log.info(f"   ✓ {len(patients)} patients registered")
    return patient_ids


def seed_appointments(cur, patient_ids):
    log.info("→ Seeding appointments...")
    today = date.today()
    tomorrow = today + timedelta(days=1)

    slots_data = [
        ("Dr. Adeyemi", "OPD",      today,    "09:00", 20),
        ("Dr. Adeyemi", "OPD",      today,    "09:20", 20),
        ("Dr. Adeyemi", "OPD",      today,    "10:00", 20),
        ("Dr. Nwosu",   "Surgery",  tomorrow, "09:00", 60),
        ("Dr. Fatima",  "Maternity",today,    "11:00", 20),
        ("Dr. Adeyemi", "OPD",      tomorrow, "09:00", 20),
    ]
    slot_ids = []
    for doc, dept, sdate, stime, dur in slots_data:
        cur.execute("SAVEPOINT slot_save")
        try:
            cur.execute("""
                INSERT INTO royan_appointment_slots
                  (doctor_name, department, slot_date, slot_time, duration_mins, is_available)
                VALUES (%s,%s,%s,%s::time,%s,true)
                ON CONFLICT (doctor_name, slot_date, slot_time) DO UPDATE
                  SET is_available = true
                RETURNING id
            """, (doc, dept, sdate, stime, dur))
            slot_ids.append(cur.fetchone()[0])
            cur.execute("RELEASE SAVEPOINT slot_save")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT slot_save")
            log.warning(f"   ! Slot skipped ({doc} {sdate} {stime}): {e}")

    appts = [
        (patient_ids["RYN-00247"], slot_ids[0], "Hypertension & diabetes review", "confirmed"),
        (patient_ids["RYN-00249"], slot_ids[2], "Routine cardiac follow-up",       "arrived"),
        (patient_ids["RYN-00250"], slot_ids[1], "Antenatal visit",                 "booked"),
    ]
    for pid, sid, reason, status in appts:
        cur.execute("""
            INSERT INTO royan_appointments (patient_id, slot_id, reason, status, booked_by)
            VALUES (%s,%s,%s,%s,'receptionist@royanhospital.com')
            ON CONFLICT DO NOTHING
        """, (pid, sid, reason, status))

    log.info(f"   ✓ {len(slot_ids)} slots, {len(appts)} appointments booked")
    return slot_ids


def seed_encounters(cur, patient_ids):
    log.info("→ Seeding encounters...")
    enc_ids = {}

    encounters = [
        # (mrn, type, status, triage, complaint, doctor, dept)
        ("RYN-00247", "outpatient", "lab_ordered",    "less_urgent", "Hypertension review — poorly controlled BP",             "Dr. Adeyemi",  "OPD"),
        ("RYN-00248", "emergency",  "consulting",     "urgent",      "Acute abdomen, right lower quadrant pain",               "Dr. Adeyemi",  "A&E"),
        ("RYN-00249", "outpatient", "pharmacy_dispensing", "non_urgent", "Cardiac follow-up, chest tightness on exertion",     "Dr. Adeyemi",  "OPD"),
        ("RYN-00250", "outpatient", "billing_pending","non_urgent",  "Antenatal visit — 28 weeks gestation",                   "Dr. Fatima",   "Maternity"),
        ("RYN-00251", "inpatient",  "consulting",     "urgent",      "Poorly controlled diabetes, HbA1c 11.2%",                "Dr. Nwosu",    "Inpatient Ward"),
    ]
    now = datetime.now(timezone.utc)
    for mrn, etype, status, triage, complaint, doctor, dept in encounters:
        pid = patient_ids[mrn]
        cur.execute("""
            INSERT INTO royan_encounters
              (patient_id, encounter_type, status, triage_level, chief_complaint,
               consulting_doctor, department, triage_at, consultation_at, registered_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'receptionist@royanhospital.com')
            RETURNING id
        """, (pid, etype, status, triage, complaint, doctor, dept,
              now - timedelta(hours=2), now - timedelta(hours=1)))
        enc_ids[mrn] = cur.fetchone()[0]

    log.info(f"   ✓ {len(enc_ids)} encounters created")
    return enc_ids


def seed_lab_orders(cur, patient_ids, enc_ids):
    log.info("→ Seeding lab orders and results...")
    now = datetime.now(timezone.utc)

    orders = [
        # Emeka Okafor — the main demo patient
        ("RYN-00247", "Full Blood Count",      "FBC",    "routine", "resulted",
         {"WBC": "6.2", "RBC": "4.8", "HGB": "13.9", "HCT": "41.2", "PLT": "210"},
         "All values within normal range", "4.5-11.0 x10³/µL", "normal"),

        ("RYN-00247", "Random Blood Sugar",    "RBS",    "urgent",  "resulted",
         {"glucose_mmol_L": "9.2"},
         "RBS 9.2 mmol/L — elevated, consistent with poor glycaemic control",
         "3.9-7.8 mmol/L", "abnormal"),

        ("RYN-00247", "Lipid Profile",         "LIPID",  "routine", "resulted",
         {"total_cholesterol": "6.8", "LDL": "4.1", "HDL": "0.9", "triglycerides": "2.3"},
         "LDL elevated at 4.1 mmol/L — cardiovascular risk", "<3.4 mmol/L LDL", "abnormal"),

        # Halima Bello — emergency
        ("RYN-00248", "Full Blood Count",      "FBC",    "stat",    "sample_collected",
         {}, "", "", None),

        ("RYN-00248", "Urinalysis",            "URINE",  "stat",    "ordered",
         {}, "", "", None),

        # Tunde Adewale — inpatient
        ("RYN-00251", "HbA1c",                "HBA1C",  "routine", "resulted",
         {"hba1c_percent": "11.2"},
         "HbA1c 11.2% — severely uncontrolled diabetes", "<7.0%", "critical"),

        ("RYN-00251", "Renal Function Test",   "RFT",    "routine", "resulted",
         {"creatinine": "102", "urea": "5.8", "eGFR": "68"},
         "Mild renal impairment — eGFR 68", "60-120 mL/min", "abnormal"),
    ]

    order_ids = {}
    for mrn, test, code, urgency, status, result_data, summary, ref_range, interp in orders:
        pid = patient_ids[mrn]
        eid = enc_ids[mrn]
        cur.execute("""
            INSERT INTO royan_lab_orders
              (encounter_id, patient_id, test_name, test_code, urgency, status,
               ordered_by, sample_type, sample_collected_at)
            VALUES (%s,%s,%s,%s,%s,%s,'Dr. Adeyemi','venous blood',%s)
            RETURNING id
        """, (eid, pid, test, code, urgency, status,
              now - timedelta(hours=1) if status != "ordered" else None))
        oid = cur.fetchone()[0]
        order_ids[(mrn, code)] = oid

        if interp and result_data:
            is_critical = interp == "critical"
            cur.execute("""
                INSERT INTO royan_lab_results
                  (lab_order_id, patient_id, result_data, result_summary,
                   reference_range, interpretation, resulted_by, is_critical)
                VALUES (%s,%s,%s,%s,%s,%s,'lab.tech@royanhospital.com',%s)
                ON CONFLICT DO NOTHING
            """, (oid, pid, psycopg2.extras.Json(result_data),
                  summary, ref_range, interp, is_critical))

    log.info(f"   ✓ {len(orders)} lab orders, results entered (abnormal flags set)")
    return order_ids


def seed_prescriptions(cur, patient_ids, enc_ids):
    log.info("→ Seeding prescriptions and dispensing...")
    now = datetime.now(timezone.utc)

    rxs = [
        # Emeka Okafor
        ("RYN-00247", "Metformin 500mg",    None, "500mg",  "Twice daily",  "3 months", "oral",     60, "tablet", "dr.adeyemi@royanhospital.com", "dispensed"),
        ("RYN-00247", "Amlodipine 10mg",    None, "10mg",   "Once daily",   "3 months", "oral",     30, "tablet", "dr.adeyemi@royanhospital.com", "dispensed"),
        # Chidi Eze
        ("RYN-00249", "Atorvastatin 40mg",  None, "40mg",   "Once at night","3 months", "oral",     30, "tablet", "dr.adeyemi@royanhospital.com", "dispensed"),
        ("RYN-00249", "Aspirin 75mg",       None, "75mg",   "Once daily",   "3 months", "oral",     30, "tablet", "dr.adeyemi@royanhospital.com", "pending"),
        # Tunde Adewale
        ("RYN-00251", "Insulin Glargine",   None, "20 units","Once daily at bedtime","1 month","im",30, "vial",  "dr.adeyemi@royanhospital.com", "pending"),
    ]

    rx_ids = {}
    for mrn, drug, code, dose, freq, dur, route, qty, unit, prescriber, status in rxs:
        pid = patient_ids[mrn]
        eid = enc_ids[mrn]
        cur.execute("""
            INSERT INTO royan_prescriptions
              (encounter_id, patient_id, drug_name, drug_code, dosage, frequency,
               duration, route, quantity, unit, prescribed_by, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (eid, pid, drug, code, dose, freq, dur, route, qty, unit, prescriber, status))
        rx_id = cur.fetchone()[0]
        rx_ids[(mrn, drug)] = rx_id

        if status == "dispensed":
            cur.execute("""
                INSERT INTO royan_dispensing
                  (prescription_id, patient_id, drug_name, batch_number, expiry_date,
                   quantity_dispensed, unit, dispensed_by, unit_cost, counselling_given)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'pharmacist@royanhospital.com',%s,true)
                ON CONFLICT DO NOTHING
            """, (rx_id, pid, drug, f"BN-2024-{pid}",
                  date.today() + timedelta(days=730),
                  qty, unit,
                  150 if "Metformin" in drug else 200))

    log.info(f"   ✓ {len(rxs)} prescriptions, dispensing records created")
    return rx_ids


def seed_billing(cur, patient_ids, enc_ids):
    log.info("→ Seeding billing records...")
    today = date.today()
    now = datetime.now(timezone.utc)

    bills = [
        # (mrn, bill_no, consult, lab, pharma, ward, proc, misc, discount, hmo, status, method)
        ("RYN-00247", "BILL-00247", 5000, 6000, 3500, 0,    0,    0,    0,    2000,  "partial", "hmo"),
        ("RYN-00248", "BILL-00248", 5000, 3000, 0,    8000, 15000,0,    0,    0,     "pending", None),
        ("RYN-00249", "BILL-00249", 5000, 4000, 2500, 0,    0,    0,    1500, 5000,  "paid",    "hmo"),
        ("RYN-00250", "BILL-00250", 3500, 2000, 0,    0,    0,    500,  0,    3000,  "pending", None),
        ("RYN-00251", "BILL-00251", 5000, 8000, 12000,25000,0,    0,    0,    20000, "pending", None),
    ]

    bill_ids = {}
    for mrn, bno, consult, lab, pharma, ward, proc, misc, disc, hmo, status, method in bills:
        pid = patient_ids[mrn]
        eid = enc_ids[mrn]
        cur.execute("""
            INSERT INTO royan_billing
              (encounter_id, patient_id, bill_number, consultation_fee, lab_charges,
               pharmacy_charges, ward_charges, procedure_charges, miscellaneous,
               discount, hmo_covered, status, payment_method, billed_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'finance@royanhospital.com')
            ON CONFLICT (bill_number) DO UPDATE SET status = EXCLUDED.status
            RETURNING id
        """, (eid, pid, bno, consult, lab, pharma, ward, proc, misc,
              disc, hmo, status, method))
        bid = cur.fetchone()[0]
        bill_ids[mrn] = bid

        if status == "paid":
            subtotal = consult + lab + pharma + ward + proc + misc
            patient_share = subtotal - disc - hmo
            cur.execute("""
                INSERT INTO royan_payments
                  (billing_id, patient_id, amount, payment_method, reference, received_by)
                VALUES (%s,%s,%s,'hmo','HMO-PAY-00249','finance@royanhospital.com')
                ON CONFLICT DO NOTHING
            """, (bid, pid, patient_share))

    log.info(f"   ✓ {len(bills)} billing records (Okafor partial, Eze paid, others pending)")
    return bill_ids


def seed_staff(cur):
    log.info("→ Seeding staff registry...")
    staff = [
        ("STF-001", "Dr. Oluwaseun Adeyemi",  "OPD",         "Consultant Physician",  "full_time", "dr.adeyemi@royanhospital.com",    350000),
        ("STF-002", "Dr. Ngozi Fatima",        "Maternity",   "Obstetrician",          "full_time", "dr.fatima@royanhospital.com",      380000),
        ("STF-003", "Dr. Emeka Nwosu",         "Surgery",     "Consultant Surgeon",    "full_time", "dr.nwosu@royanhospital.com",       420000),
        ("STF-004", "Nurse Bisi Akinwale",     "Ward A",      "Senior Nurse",          "full_time", "nurse@royanhospital.com",          180000),
        ("STF-005", "Pharmacy Tech Chuka",     "Pharmacy",    "Pharmacist",            "full_time", "pharmacist@royanhospital.com",     220000),
        ("STF-006", "Lab Tech Amara Obi",      "Laboratory",  "Lab Technician",        "full_time", "lab.tech@royanhospital.com",       190000),
        ("STF-007", "Mrs. Kemi Ola",           "Finance",     "Finance Officer",       "full_time", "finance@royanhospital.com",        200000),
        ("STF-008", "Miss Fatou Diallo",       "Front Desk",  "Receptionist",          "full_time", "receptionist@royanhospital.com",   150000),
    ]
    today = date.today()
    for sno, name, dept, desig, etype, email, salary in staff:
        cur.execute("""
            INSERT INTO royan_staff
              (staff_number, full_name, department, designation,
               employment_type, email, monthly_gross, joined_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (staff_number) DO UPDATE SET email = EXCLUDED.email
        """, (sno, name, dept, desig, etype, email, salary,
              today - timedelta(days=365)))
    log.info(f"   ✓ {len(staff)} staff members seeded")


def seed_alerts(cur):
    log.info("→ Seeding system alerts...")
    alerts = [
        ("Lab TAT Alert",              "Average RBS TAT today is 52 min — exceeds 45-min target. Review lab workflow.",                  "warning",  "lab"),
        ("Expiry Warning",             "Batch AMX-2024-09 (Amoxicillin 500mg) expires in 14 days — 120 units remaining.",               "warning",  "pharmacy"),
        ("Bed Capacity — Ward B",      "Ward B at 87% occupancy (13/15 beds). Recommend admissions to Ward A.",                         "warning",  "clinical"),
        ("HMO Reconciliation",         "3 invoices have HMO coverage discrepancies — billed amount does not match fee schedule.",        "warning",  "finance"),
        ("High-Value Lab Result",      "Patient RYN-00251: HbA1c 11.2% — critical. Endocrinology review recommended.",                  "critical", "clinical"),
        ("Staff Overtime Alert",       "Dr. Adeyemi has logged 62 hours this week — exceeds 60-hour limit.",                            "info",     "hr"),
        ("Procurement Delivery",       "PO-2026-0042 (IV Cannula 18G x 500) expected today from Emzor Pharmaceuticals.",                "info",     "inventory"),
    ]
    for title, msg, severity, category in alerts:
        cur.execute("""
            INSERT INTO royan_alerts (title, message, severity, category, status)
            VALUES (%s,%s,%s,%s,'unread')
        """, (title, msg, severity, category))
    log.info(f"   ✓ {len(alerts)} demo alerts seeded")


def seed_inventory_expiry_alert(cur):
    """Seed a near-expiry drug batch into royan_procurement_shipments for the expiry agent demo."""
    log.info("→ Seeding inventory / procurement records...")
    today = date.today()
    shipments = [
        ("PO-2026-0038", "Emzor Pharma",      "Metformin 500mg tablets x 1000",      1000, "tablets",  85, today - timedelta(days=30), today - timedelta(days=28), "received"),
        ("PO-2026-0039", "Fidson Healthcare", "Amlodipine 10mg tablets x 500",         500, "tablets",  95, today - timedelta(days=15), today - timedelta(days=13), "received"),
        ("PO-2026-0040", "GSK Nigeria",       "Amoxicillin 500mg capsules x 500",      500, "capsules", 80, today - timedelta(days=60), today - timedelta(days=58), "received"),
        ("PO-2026-0041", "May & Baker",       "IV Fluids Normal Saline 0.9% x 200",   200, "bags",    450, today + timedelta(days=14), None,                       "in_transit"),
        ("PO-2026-0042", "Surgifriend",       "IV Cannula 18G x 500",                 500, "pcs",      35, today + timedelta(days=1),  None,                       "in_transit"),
    ]
    for po, supplier, item, qty, unit, ucost, expected, actual, status in shipments:
        cur.execute("""
            INSERT INTO royan_procurement_shipments
              (po_number, supplier_name, item_description, quantity, unit,
               unit_cost, expected_arrival, actual_arrival, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (po_number) DO NOTHING
        """, (po, supplier, item, qty, unit, ucost, expected, actual, status))
    log.info(f"   ✓ {len(shipments)} procurement records (near-expiry batch included)")


def seed_chat_history_migration(cur):
    """Ensure the chat history table exists (may be missing from migrations)."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.royan_chat_history (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id text,
            question text NOT NULL,
            answer text NOT NULL,
            sources jsonb DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON public.royan_chat_history(user_id)")
    log.info("   ✓ royan_chat_history table ensured")


def main():
    log.info("\n╔══════════════════════════════════════════════╗")
    log.info("║  RoyanHealth Demo Seed — Royan Hospital     ║")
    log.info("╚══════════════════════════════════════════════╝\n")

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        seed_chat_history_migration(cur)
        seed_users(cur)
        ward_ids = seed_wards_and_beds(cur)
        patient_ids = seed_patients(cur)
        seed_appointments(cur, patient_ids)
        enc_ids = seed_encounters(cur, patient_ids)
        seed_lab_orders(cur, patient_ids, enc_ids)
        seed_prescriptions(cur, patient_ids, enc_ids)
        seed_billing(cur, patient_ids, enc_ids)
        seed_staff(cur)
        seed_alerts(cur)
        seed_inventory_expiry_alert(cur)
        conn.commit()

        log.info("\n✅ Seed complete!\n")
        log.info("Demo patients:")
        log.info("  RYN-00247  Emeka Okafor    — outpatient, abnormal labs, pending bill ₦12,500")
        log.info("  RYN-00248  Halima Bello    — emergency admission, surgery pending")
        log.info("  RYN-00249  Chidi Eze       — outpatient, paid bill")
        log.info("  RYN-00250  Amina Yusuf     — antenatal, pending bill")
        log.info("  RYN-00251  Tunde Adewale   — inpatient, critical HbA1c 11.2%")
        log.info("\nStaff logins (all password: Demo1234!):")
        log.info("  dr.adeyemi@royanhospital.com   → doctor")
        log.info("  lab.tech@royanhospital.com     → lab_tech")
        log.info("  pharmacist@royanhospital.com   → pharmacist")
        log.info("  finance@royanhospital.com      → finance")
        log.info("  receptionist@royanhospital.com → receptionist")
        log.info("  nurse@royanhospital.com        → nurse")
    except Exception as e:
        conn.rollback()
        log.error(f"\n❌ Seed failed: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
