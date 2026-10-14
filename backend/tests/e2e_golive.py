"""Go-live end-to-end run (Oct 2026): a private and an HMO patient from the front desk to discharge, a Scancare
walk-in, and the books behind them - against the running stack (https://localhost).

    python tests/e2e_golive.py            # runs, prints PASS/FAIL per step, writes tests/e2e_golive_ids.json

Test patients are named "ZZTEST E2E ..." and every id created is written to e2e_golive_ids.json so the run can be
removed afterwards. Tokens are minted inside the backend container (same secret as the app).
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests
import urllib3

sys.stdout.reconfigure(encoding="utf-8")

urllib3.disable_warnings()
BASE = "https://localhost"
ADMIN = ("779b8e0d-9a8a-4bcb-a9f2-c05c0ed39235", ["admin"], "admin@royanhospital.com")
DOCTOR = ("4e2d2db0-ecff-49e3-bc15-a0850c96d133", ["doctor"], "test.doctor@royanhospital.local")
DOCTOR_STAFF_ID = "1a58d5b4-7845-40d6-86d4-abb90baf4783"
AVON_HMO_ID = 7313
LAB = {"test_name": "MALARIA PARASITE TEST(MP)", "catalog_id": 175}
SCAN = {"test_name": "ULTRASOUND ABDOMINOPELVIC", "modality": "ultrasound", "radiology_catalog_id": 3}
DRUG = {"drug_name": "PARACETAMOL 500MG TAB", "formulary_id": 333, "dosage": "1g", "frequency": "three times daily",
        "duration": "3 days", "route": "oral", "quantity": 18}
ROOM = "Consulting Room 1"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

ids: dict = {"patients": [], "encounters": [], "bills": [], "payments": [], "room_assignments": [], "insurance": []}
results: list = []


def token(who) -> str:
    sub, roles, email = who
    code = f"from src.auth_utils import create_access_token; print(create_access_token({sub!r},{roles!r},{email!r})[0])"
    return subprocess.check_output(["docker", "exec", "royan_backend", "python", "-c", code], text=True).strip()


TOK = {"admin": token(ADMIN), "doctor": token(DOCTOR)}


def call(method, path, who="admin", **kw):
    r = requests.request(method, BASE + path, headers={"Authorization": f"Bearer {TOK[who]}"}, verify=False, timeout=60, **kw)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    return r.status_code, body


def step(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  -- {detail}" if detail else ""), flush=True)
    return ok


def must(name, status, body, expect=(200, 201)):
    ok = status in expect
    step(name, ok, "" if ok else f"HTTP {status}: {str(body)[:300]}")
    return body if ok else None


def enc_status(eid):
    _, b = call("GET", f"/queue/encounters/{eid}")
    return (b.get("encounter") or b).get("status") if isinstance(b, dict) else None


def pay_all(eid, label):
    """Cashier: receive whatever the patient owes on the visit."""
    _, b = call("GET", f"/billing_hospital/bills?encounter_id={eid}")
    for bill in b.get("bills", []):
        ids["bills"].append(bill["id"])
        owed = float(bill.get("outstanding") or 0)
        if bill.get("status") in ("void", "paid") or owed <= 0.009:
            continue
        s, p = call("POST", f"/billing_hospital/bills/{bill['id']}/payment",
                    json={"amount": owed, "payment_method": "pos", "reference": "E2E"})
        if must(f"{label}: cashier receives ₦{owed:,.2f} on {bill['bill_number']}", s, p):
            pid = (p.get("payment") or {}).get("id") or p.get("payment_id")
            if pid:
                ids["payments"].append(pid)


def visit(kind: str):
    label = kind.upper()
    global PHONE
    PHONE = "080" + time.strftime("%H%M%S") + ("11" if kind == "private" else "22")   # a fresh phone: no duplicate prompt
    # ── Front desk: register a new patient (and the HMO policy) ──
    s, b = call("POST", "/patients/register", json={
        "first_name": "ZZTEST", "last_name": f"E2E {label} {time.strftime('%H%M%S')}", "date_of_birth": "1990-05-17",
        "gender": "female", "phone": PHONE, "address": "72 Aina Street, Ojodu", "next_of_kin_name": "Test Kin",
        "next_of_kin_phone": "08000000001", "blood_group": "O+", "genotype": "AA", "allergies": ["Penicillin"],
        **({"hmo_provider": "AVON", "hmo_id": "E2E-AVON-001", "patient_type": "hmo"} if kind == "hmo" else {"patient_type": "private"}),
    })
    p = must(f"{label}: front desk registers a new patient", s, b)
    if not p:
        return
    patient = p.get("patient") or p
    pid, mrn = patient["id"], patient["mrn"]
    ids["patients"].append(pid)
    if kind == "hmo":
        s, b = call("POST", "/coverage/patient-insurance", json={"patient_id": pid, "hmo_id": AVON_HMO_ID,
                                                                 "membership_id": "E2E-AVON-001", "is_primary": True, "status": "active"})
        ins = must("HMO: AVON policy attached to the patient", s, b)
        if ins:
            ids["insurance"].append((ins.get("policy") or ins).get("id"))

    s, prof = call("GET", f"/patients/{mrn}/profile")
    pc = (prof or {}).get("patient", {}) if s == 200 else {}
    step(f"{label}: new patient opens in the PCE with every field saved", s == 200 and pc.get("phone") == PHONE
         and (pc.get("blood_group") == "O+") and (pc.get("genotype") == "AA") and "Penicillin" in str(pc.get("allergies")),
         f"profile keys: phone={pc.get('phone')} blood={pc.get('blood_group')} genotype={pc.get('genotype')} allergies={pc.get('allergies')}")

    # ── Front desk: check-in with the doctor (room comes from today's assignment) and priority ──
    s, b = call("POST", "/queue/encounters", json={
        "patient_id": pid, "department": "OPD", "encounter_type": "outpatient", "chief_complaint": "Fever and headache for 3 days",
        "payer_type": kind if kind == "hmo" else "private", "membership_id": "E2E-AVON-001" if kind == "hmo" else None,
        "priority": "urgent", "doctor_id": DOCTOR_STAFF_ID})
    e = must(f"{label}: front desk checks the patient in", s, b)
    if not e:
        return
    enc = e.get("encounter") or e
    eid = enc["id"]
    ids["encounters"].append(eid)
    step(f"{label}: queue number issued", str(enc.get("queue_number") or "").startswith("OPD-"), enc.get("queue_number"))
    step(f"{label}: priority set at the desk is the triage (no re-triage)", enc.get("status") == "triaged" and enc.get("triage_level") == "urgent",
         f"status={enc.get('status')} triage={enc.get('triage_level')}")
    step(f"{label}: doctor and today's room attached", enc.get("doctor_id") == DOCTOR_STAFF_ID and enc.get("consulting_room") == ROOM,
         f"doctor={enc.get('consulting_doctor')} room={enc.get('consulting_room')}")
    fd_bill = e.get("bill") or {}
    fb = fd_bill.get("bill") or fd_bill
    if kind == "hmo":
        step("HMO: front-desk bill goes to the HMO in full (patient pays ₦0)", float(fb.get("hmo_covered") or 0) > 0 and float(fb.get("patient_balance") or 0) == 0,
             f"hmo={fb.get('hmo_covered')} patient={fb.get('patient_balance')}")
    else:
        step("PRIVATE: front-desk bill raised for the patient", float(fb.get("patient_balance") or 0) > 0, f"patient={fb.get('patient_balance')}")
        _, ql = call("GET", "/queue/encounters?active_only=true")
        row = next((x for x in ql.get("encounters", []) if x["id"] == eid), {})
        step("PRIVATE: queue shows 'to pay first' before vitals", bool(row.get("pay_first")), str(row.get("pay_first")))
        call("POST", "/nursing/vitals", json={"patient_id": pid, "encounter_id": eid, "temperature": 37.0})
        s, b = call("POST", f"/queue/encounters/{eid}/nurse-done", json={})
        step("PRIVATE: unpaid - nurse cannot send the patient to the doctor", s == 402, f"HTTP {s}: {str(b)[:160]}")
        s, b = call("POST", f"/queue/encounters/{eid}/consult", who="doctor", json={"doctor_id": DOCTOR_STAFF_ID})
        step("PRIVATE: unpaid - doctor cannot start the consultation", s in (402, 409), f"HTTP {s}: {str(b)[:160]}")
        pay_all(eid, label)

    s, q = call("GET", f"/queue/doctors-today")
    me = next((d for d in (q or {}).get("doctors", []) if d["id"] == DOCTOR_STAFF_ID), {})
    step(f"{label}: doctor shows on seat in {ROOM} with the patient waiting", me.get("on_seat") and me.get("room") == ROOM and me.get("waiting", 0) >= 1,
         f"on_seat={me.get('on_seat')} room={me.get('room')} waiting={me.get('waiting')}")
    s, dq = call("GET", f"/queue/encounters?active_only=true&doctor={DOCTOR_STAFF_ID}", who="doctor")
    step(f"{label}: patient on the doctor's own queue", s == 200 and any(x["id"] == eid for x in dq.get("encounters", [])))

    # ── Nurse: vitals ──
    s, b = call("POST", "/nursing/vitals", json={"patient_id": pid, "encounter_id": eid, "bp_systolic": 120, "bp_diastolic": 80,
                                                  "temperature": 38.4, "pulse": 96, "spo2": 98, "respiratory_rate": 18, "weight": 64})
    must(f"{label}: nurse records vitals", s, b)
    s, b = call("POST", f"/queue/encounters/{eid}/nurse-done", json={})
    must(f"{label}: vitals done, patient ready for the doctor", s, b)
    step(f"{label}: status is ready for doctor", enc_status(eid) == "nurse_assessment", enc_status(eid))

    # ── Doctor: consult, SOAP note with ICD-10, orders ──
    s, b = call("POST", f"/queue/encounters/{eid}/consult", who="doctor", json={"doctor_id": DOCTOR_STAFF_ID})
    must(f"{label}: doctor starts the consultation", s, b)
    s, sug = call("GET", "/clinical/icd10/suggest?text=" + requests.utils.quote("fever headache malaria"), who="doctor")
    codes = [c["code"] for c in (sug or {}).get("codes", [])]
    step(f"{label}: ICD-10 suggested from the note", any(c.startswith("B5") for c in codes), ", ".join(codes[:5]))
    s, b = call("POST", f"/queue/encounters/{eid}/notes", who="doctor", json={
        "note_type": "soap", "content": "SOAP note", "subjective": "Fever and headache x3/7",
        "objective": "T 38.4, mild pallor", "assessment": "Primary: Malaria (Plasmodium falciparum) [B50]",
        "plan": "MP test, scan, paracetamol", "icd10_codes": ["B50"]})
    n = must(f"{label}: doctor signs the SOAP note", s, b)
    step(f"{label}: note is signed by the doctor", bool(((n or {}).get("note") or {}).get("signed_at")))
    s, lab = call("POST", "/lab/orders", who="doctor", json={"patient_id": pid, "encounter_id": eid, "urgency": "routine", **LAB})
    lab = must(f"{label}: doctor orders a lab test", s, lab)
    lab_id = ((lab or {}).get("order") or lab or {}).get("id")
    s, rad = call("POST", "/radiology/orders", who="doctor", json={"patient_id": pid, "encounter_id": eid, "urgency": "routine",
                                                                   "clinical_indication": "Abdominal pain", **SCAN})
    rad = must(f"{label}: doctor orders a Scancare scan", s, rad)
    rad_id = ((rad or {}).get("order") or rad or {}).get("id")
    s, rx = call("POST", "/pharmacy/prescriptions", who="doctor", json={"patient_id": pid, "encounter_id": eid, **DRUG})
    rx = must(f"{label}: doctor prescribes", s, rx)
    rx_id = ((rx or {}).get("prescription") or rx or {}).get("id")
    s, b = call("POST", f"/queue/encounters/{eid}/end-consultation", who="doctor", json={"review_results": True})
    must(f"{label}: doctor ends consultation - see again with results", s, b)
    step(f"{label}: visit waits for results", enc_status(eid) == "lab_ordered", enc_status(eid))

    # ── Cashier: the orders are billed (Royan + Scancare) ──
    s, b = call("POST", f"/queue/encounters/{eid}/send-to-cashier", json={})
    must(f"{label}: orders sent to the cashier (bills raised)", s, b)
    _, bl = call("GET", f"/billing_hospital/bills?encounter_id={eid}")
    ents = {x.get("entity") for x in bl.get("bills", []) if x.get("status") != "void"}
    step(f"{label}: Royan and Scancare bills raised separately", {"ROYAN", "SCANCARE"} <= ents, str(ents))
    if kind == "hmo":
        owe = sum(float(x.get("outstanding") or 0) for x in bl.get("bills", []) if x.get("status") != "void")
        step("HMO: patient owes nothing at the till", owe <= 0.009, f"owes ₦{owe:,.2f}")
        step("HMO: every bill tagged HMO with AVON and the card", all(x.get("payer_type") == "hmo" and x.get("hmo_name") for x in bl["bills"]),
             str([(x["bill_number"], x.get("payer_type"), x.get("hmo_name")) for x in bl["bills"]]))
    else:
        if lab_id:
            s, b = call("POST", f"/lab/orders/{lab_id}/collect", json={})
            step("PRIVATE: unpaid - lab cannot take the sample", s == 402, f"HTTP {s}: {str(b)[:160]}")
        if rad_id:
            call("PATCH", f"/radiology/orders/{rad_id}/status", json={"status": "scheduled"})
            s, b = call("PATCH", f"/radiology/orders/{rad_id}/status", json={"status": "in_progress"})
            step("PRIVATE: unpaid - Scancare cannot start the scan", s == 402, f"HTTP {s}: {str(b)[:160]}")
        if rx_id:
            s, b = call("POST", f"/pharmacy/prescriptions/{rx_id}/dispense", json={"quantity_dispensed": DRUG["quantity"], "override_allergy": True, "acknowledge_ddi": True})
            step("PRIVATE: unpaid - pharmacy cannot dispense", s == 402, f"HTTP {s}: {str(b)[:160]}")
        pay_all(eid, label)

    # ── Lab: sample, result, verify -> back to the doctor ──
    if lab_id:
        for st, path, body in (("collects the sample", "collect", {}), ("receives the sample", "receive", {}),
                               ("enters the result", "result", {"result_value": "Positive (++)", "result_unit": "",
                                                                 "result_summary": "P. falciparum seen", "is_critical": False}),
                               ("verifies the result", "verify", {})):
            s, b = call("POST", f"/lab/orders/{lab_id}/{path}", json=body)
            must(f"{label}: lab {st}", s, b)
        step(f"{label}: results ready - doctor review", enc_status(eid) == "awaiting_results", enc_status(eid))

    # ── Scancare: scan reported ──
    if rad_id:
        for stt in ("scheduled", "in_progress", "completed"):
            call("PATCH", f"/radiology/orders/{rad_id}/status", json={"status": stt})
        s, b = call("PATCH", f"/radiology/orders/{rad_id}/report", json={"report": "Normal abdominopelvic scan.", "impression": "Normal"})
        must(f"{label}: Scancare reports the scan", s, b)

    # ── Doctor reviews results and ends ──
    s, b = call("POST", f"/queue/encounters/{eid}/consult", who="doctor", json={"doctor_id": DOCTOR_STAFF_ID})
    must(f"{label}: doctor opens the results review", s, b)
    s, b = call("POST", f"/queue/encounters/{eid}/end-consultation", who="doctor", json={"review_results": False})
    must(f"{label}: doctor ends the consultation", s, b)

    # ── Pharmacy dispenses (patient signs) ──
    if rx_id:
        s, d = call("POST", f"/pharmacy/prescriptions/{rx_id}/dispense", json={"quantity_dispensed": DRUG["quantity"], "counselling_given": True,
                                                                               "override_allergy": True, "acknowledge_ddi": True})
        d = must(f"{label}: pharmacy dispenses", s, d)
        did = ((d or {}).get("dispensing") or d or {}).get("id")
        if did:
            r = requests.post(f"{BASE}/pharmacy/dispensing/{did}/signature", headers={"Authorization": f"Bearer {TOK['admin']}"},
                              files={"file": ("signature.png", PNG, "image/png")}, verify=False, timeout=60)
            step(f"{label}: patient signs for the drugs at the pharmacy", r.status_code == 200, r.text[:200])

    # department queues: finished work leaves the to-do list and shows under "done today"
    for name, path, key, oid in (("lab", "/lab/orders", "orders", lab_id), ("Scancare", "/radiology/orders", "orders", rad_id),
                                 ("pharmacy", "/pharmacy/prescriptions", "prescriptions", rx_id)):
        if not oid:
            continue
        _, act = call("GET", f"{path}?view=active&limit=200")
        _, done = call("GET", f"{path}?view=done&limit=200")
        in_act = any(x["id"] == oid for x in act.get(key, []))
        in_done = any(x["id"] == oid for x in done.get(key, []))
        step(f"{label}: {name} queue - finished item moved to 'done today'", in_done and not in_act, f"active={in_act} done={in_done}")

    st = enc_status(eid)
    step(f"{label}: visit is done - pay & discharge", st == "billing_pending", st)

    # ── HMO desk: claims form ──
    if kind == "hmo":
        s, desk = call("GET", "/coverage/hmo-desk")
        row = next((r for r in (desk or {}).get("patients", []) if r["encounter_id"] == eid), None)
        step("HMO: patient on the HMO Desk with AVON, card, drugs dispensed and signature", bool(row) and row["hmo_name"] == "AVON"
             and row["membership_id"] == "E2E-AVON-001" and row["drugs_dispensed"] == 1 and row["signed"],
             str({k: row.get(k) for k in ("hmo_name", "membership_id", "drugs_dispensed", "signed", "hmo_share", "patient_owes")}) if row else "missing")
        if row and row.get("claim_bill_id"):
            s, f = call("GET", f"/billing_hospital/bills/{row['claim_bill_id']}/claims-form")
            step("HMO: claims form filled from the visit", s == 200 and f.get("hmo_name") == "AVON" and f.get("health_card_no") == "E2E-AVON-001"
                 and "alaria" in (f.get("primary_diagnosis") or "") and f.get("investigations") and f.get("medications")
                 and f.get("patient_signature_url", "").startswith("data:image"),
                 str({k: (str(f.get(k))[:60]) for k in ("hmo_name", "health_card_no", "primary_diagnosis", "total")}))
            s, b = call("POST", f"/coverage/hmo-desk/{eid}/verify", json={"verified": True})
            must("HMO: officer verifies the claim", s, b)

    # ── Discharge: only when nothing is owed ──
    if kind == "private":
        pay_all(eid, label)   # anything billed after dispensing
    s, b = call("POST", f"/queue/encounters/{eid}/discharge", json={"discharge_summary": "Treated for malaria. Review in 1 week.",
                                                                    "disposition": "home"})
    must(f"{label}: patient discharged", s, b)
    step(f"{label}: leaves the active queue", enc_status(eid) == "discharged", enc_status(eid))
    _, aq = call("GET", "/queue/encounters?active_only=true&limit=200")
    step(f"{label}: no longer on Queue & Flow's main list", not any(x["id"] == eid for x in aq.get("encounters", [])))
    if kind == "hmo":
        _, dk = call("GET", "/coverage/hmo-desk")
        row = next((r for r in dk.get("patients", []) if r["encounter_id"] == eid), None)
        step("HMO: HMO Desk moves the patient to 'Discharged today'", bool(row) and row["status"] == "discharged", str(row and row["status"]))

    # ── The books ──
    check_books(label, eid)


def check_books(label, eid):
    sql = f"""SELECT p.source_type, p.status, p.message FROM fin_source_postings p
              WHERE (p.source_type IN ('BILL','BILL_VOID') AND p.source_id IN (SELECT id::text FROM royan_billing WHERE encounter_id={eid}))
                 OR (p.source_type='PAYMENT' AND p.source_id IN (SELECT y.id::text FROM royan_payments y JOIN royan_billing b ON b.id=y.billing_id WHERE b.encounter_id={eid}))
                 OR (p.source_type='DISPENSING' AND p.source_id IN (SELECT d.id::text FROM royan_dispensing d JOIN royan_prescriptions r ON r.id=d.prescription_id WHERE r.encounter_id={eid}))
              ORDER BY 1"""
    out = subprocess.check_output(["docker", "exec", "royan_db", "psql", "-U", "postgres", "-d", "synbot_health", "-Atc", sql], text=True)
    rows = [l.split("|") for l in out.strip().splitlines() if l]
    kinds = {r[0] for r in rows if r[1] == "POSTED"}
    bad = [r for r in rows if r[1] != "POSTED"]
    need = {"BILL", "DISPENSING"} | ({"PAYMENT"} if label == "PRIVATE" else set())
    step(f"{label}: bills, receipts and dispensing posted to Roy Books", need <= kinds and not bad,
         f"posted={sorted(kinds)} not-posted={bad}")
    if label == "HMO":
        step("HMO: invoices posted against the HMO (receivable from AVON)", any(r[0] == "BILL" and "-HMO" in r[2] for r in rows),
             str([r[2] for r in rows if r[0] == "BILL"]))


def scancare_walk_in():
    s, b = call("POST", "/patients/register", json={"first_name": "ZZTEST", "last_name": f"E2E SCANCARE {time.strftime('%H%M%S')}",
                                                    "gender": "male", "date_of_birth": "1985-01-01", "phone": "081" + time.strftime("%H%M%S") + "99"})
    p = must("SCANCARE: walk-in patient registered", s, b)
    if not p:
        return
    pid = (p.get("patient") or p)["id"]
    ids["patients"].append(pid)
    s, b = call("POST", "/radiology/scancare/walk-in", json={"patient_id": pid, "studies": [SCAN["radiology_catalog_id"]],
                                                             "clinical_indication": "Walk-in scan"})
    w = must("SCANCARE: walk-in study booked and billed on Scancare", s, b)
    bill = ((w or {}).get("bill") or {})
    bill = bill.get("bill") or bill
    if bill.get("id"):
        ids["bills"].append(bill["id"])
        step("SCANCARE: bill is Scancare's (own numbering, own company)", bill.get("entity") == "SCANCARE", f"{bill.get('bill_number')} {bill.get('entity')}")
        s, r = call("POST", f"/billing_hospital/bills/{bill['id']}/payment", json={"amount": float(bill.get("patient_balance") or 0),
                                                                                   "payment_method": "transfer", "reference": "E2E"})
        must("SCANCARE: cashier receives payment", s, r)
        out = subprocess.check_output(["docker", "exec", "royan_db", "psql", "-U", "postgres", "-d", "synbot_health", "-Atc",
                                       f"""SELECT p.source_type||':'||p.status||':'||e.code FROM fin_source_postings p JOIN fin_legal_entities e ON e.id=p.legal_entity_id
                                           WHERE (p.source_type='BILL' AND p.source_id='{bill['id']}')
                                              OR (p.source_type='PAYMENT' AND p.source_id IN (SELECT id::text FROM royan_payments WHERE billing_id={bill['id']}))"""], text=True)
        step("SCANCARE: bill and receipt posted to Scancare's books (SCN)", "BILL:POSTED:SCN" in out and "PAYMENT:POSTED:SCN" in out, out.strip().replace("\n", " "))


def main():
    s, b = call("POST", "/queue/room-assignments", json={"doctor_id": DOCTOR_STAFF_ID, "room": ROOM})
    a = must(f"Front desk assigns Dr. Test Doctor to {ROOM}", s, b)
    if a:
        ids["room_assignments"].append((a.get("assignment") or {}).get("id"))
    try:
        for kind in ("private", "hmo"):
            try:
                visit(kind)
            except Exception as exc:   # report and carry on with the next journey
                step(f"{kind.upper()}: journey crashed", False, repr(exc))
        try:
            scancare_walk_in()
        except Exception as exc:
            step("SCANCARE: journey crashed", False, repr(exc))
    finally:
        Path(__file__).with_name("e2e_golive_ids.json").write_text(json.dumps(ids, indent=2, default=str))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    for n, _, d in failed:
        print(f"  FAIL {n}: {d}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
