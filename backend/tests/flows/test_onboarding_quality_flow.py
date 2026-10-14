"""Staff onboarding never duplicates a person in HR; compliance and pharmacy QC read real records."""
import uuid

import pytest

from src.fin.db import q1
from src.services import quality_hub, staff_onboarding



def _registration(conn, full_name, email, role="doctor"):
    return q1(conn, """INSERT INTO royan_staff_registrations (email, hashed_password, full_name, role, department, designation, phone, kyc_details, status)
                       VALUES (%s, 'x', %s, %s, 'Gynaecology', 'Consultant', '0800', '{"specialty": "Obstetrics"}'::jsonb, 'pending')
                       RETURNING *""", (email, full_name, role))


def _hr_record(conn, full_name, email=None):
    return q1(conn, """INSERT INTO royan_staff (staff_number, full_name, email, department, designation, role)
                       VALUES (%s, %s, %s, 'Gynaecology', 'Staff', 'doctor') RETURNING id::text AS id""",
              ("FLOW-" + uuid.uuid4().hex[:6], full_name, email))["id"]


def test_registration_links_to_the_existing_hr_record_by_name(conn, make_user):
    ADMIN = make_user("admin")["sub"]
    staff_id = _hr_record(conn, "Fumilayo Akinlade")                      # HR has her, without an email
    reg = _registration(conn, "Dr. Akinlade Fumilayo", f"fumi-{uuid.uuid4().hex[:6]}@example.test")
    m = staff_onboarding.hr_matches(reg)
    assert m and m[0]["id"] == staff_id and m[0]["why"] == "same name"
    with pytest.raises(staff_onboarding.OnboardingError):              # a likely match must be confirmed
        staff_onboarding.approve(reg, ADMIN, None, False)
    out = staff_onboarding.approve(reg, ADMIN, staff_id, False)
    assert out["mode"] == "linked" and out["staff_id"] == staff_id
    row = q1(conn, "SELECT user_id::text AS u, email, designation, specialty FROM royan_staff WHERE id::text=%s", (staff_id,))
    assert row["u"] == out["user_id"] and row["email"] == reg["email"]
    assert row["designation"] == "Consultant" and row["specialty"] == "Obstetrics"   # filled what HR lacked
    n = q1(conn, "SELECT COUNT(*) AS n FROM royan_staff WHERE lower(full_name) LIKE '%%akinlade%%'")["n"]
    assert n == 1                                                         # one person, one record


def test_same_email_always_links_and_new_person_gets_one_record(conn, make_user):
    ADMIN = make_user("admin")["sub"]
    email = f"tayo-{uuid.uuid4().hex[:6]}@example.test"
    staff_id = _hr_record(conn, "Tayo Bello", email)
    reg = _registration(conn, "Omotayo Bello", email)
    out = staff_onboarding.approve(reg, ADMIN, None, True)             # admin said "new" - email wins
    assert out["mode"] == "linked" and out["staff_id"] == staff_id
    reg2 = _registration(conn, "Zainab Quadri-Flowtest", f"z-{uuid.uuid4().hex[:6]}@example.test", role="nurse")
    out2 = staff_onboarding.approve(reg2, ADMIN, None, True)
    assert out2["mode"] == "created"
    assert q1(conn, "SELECT role FROM royan_staff WHERE id::text=%s", (out2["staff_id"],))["role"] == "nurse"
    with pytest.raises(staff_onboarding.OnboardingError):                # the login now exists
        staff_onboarding.approve({**reg2, "id": uuid.uuid4()}, ADMIN, None, True)


def test_compliance_and_pharmacy_qc_read_real_records(conn):
    c = quality_hub.compliance()
    assert 0 <= c["compliance_score"] <= 100
    assert c["compliance_score"] == max(0, 100 - sum(d["points"] for d in c["deductions"]))
    qc = quality_hub.pharmacy_qc()
    shelf = q1(conn, """SELECT COUNT(*) FILTER (WHERE expiry_date < CURRENT_DATE) AS n FROM royan_inventory_batches
                        WHERE quantity_on_hand > 0""")["n"]
    assert qc["expired"]["batches"] == shelf
    assert all(0 <= x["days_left"] <= 90 for x in qc["expiring"])
