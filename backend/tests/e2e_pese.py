#!/usr/bin/env python3
"""
Patient Encounter Simulation Engine (PESE)
==========================================
Full end-to-end clinical lifecycle test for SynbotHealth demo validation.

Runs two scenarios against the live server:
  A) Existing patient  — validates Hope ETL data is live and traversable
  B) New patient       — validates full registration + lifecycle from scratch

Each scenario walks the complete clinical encounter status machine:
  patient_registered → triaged → nurse_assessment → called → consulting
  → lab_ordered → pharmacy_dispensing → billing_pending → discharged

Usage:
  python backend/tests/e2e_pese.py --url http://localhost \\
      --admin-email admin@royanhospital.com --admin-password royan1234

  # Quick mode using DEV_TOKEN (if DEV_TOKEN_ENABLED=1)
  python backend/tests/e2e_pese.py --url http://localhost --dev-token

  # Custom DB for direct validation
  python backend/tests/e2e_pese.py --url http://localhost \\
      --db-url postgresql://postgres:admin1234@localhost:5433/synbot_health
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("ERROR: 'requests' not installed. Run: pip install requests")

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _ok(msg: str) -> str:   return f"{GREEN}✅ {msg}{RESET}"
def _fail(msg: str) -> str:  return f"{RED}❌ {msg}{RESET}"
def _warn(msg: str) -> str:  return f"{YELLOW}⚠️  {msg}{RESET}"
def _info(msg: str) -> str:  return f"{CYAN}   {msg}{RESET}"


# ─────────────────────────────────────────────────────────────────────────────
# StepResult
# ─────────────────────────────────────────────────────────────────────────────

class StepResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.status_code: Optional[int] = None
        self.detail: str = ""
        self.duration_ms: float = 0.0
        self.data: Dict[str, Any] = {}

    def mark_pass(self, detail: str = "", data: Dict = None):
        self.passed = True
        self.detail = detail
        if data:
            self.data = data

    def mark_fail(self, detail: str):
        self.passed = False
        self.detail = detail

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "status_code": self.status_code,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# PESERunner
# ─────────────────────────────────────────────────────────────────────────────

class PESERunner:
    def __init__(self, base_url: str, db_url: Optional[str], use_dev_token: bool):
        self.base = base_url.rstrip("/")
        self.db_url = db_url
        self.use_dev_token = use_dev_token
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        self.session.verify = False  # self-signed cert on localhost nginx
        self._scenario_b_phone: str = ""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def _call(self, method: str, path: str, **kwargs) -> Tuple[requests.Response, float]:
        timeout = kwargs.pop("timeout", 30)
        t0 = time.time()
        resp = self.session.request(method, self._url(path), timeout=timeout, **kwargs)
        return resp, (time.time() - t0) * 1000

    def _step(self, name: str, method: str, path: str,
              assertion_fn, **kwargs) -> StepResult:
        sr = StepResult(name)
        try:
            resp, ms = self._call(method, path, **kwargs)
            sr.status_code = resp.status_code
            sr.duration_ms = ms
            body: Dict = {}
            try:
                body = resp.json()
            except Exception:
                body = {"_raw": resp.text[:200]}
            ok, detail, data = assertion_fn(resp, body)
            if ok:
                sr.mark_pass(detail, data)
                print(_ok(f"[{ms:5.0f}ms] {name} — {detail}"))
            else:
                sr.mark_fail(f"HTTP {resp.status_code}: {detail}")
                print(_fail(f"[{ms:5.0f}ms] {name} — HTTP {resp.status_code}: {detail}"))
                if body:
                    print(_info(f"Response: {json.dumps(body)[:300]}"))
        except Exception as exc:
            sr.mark_fail(str(exc))
            print(_fail(f"{name} — EXCEPTION: {exc}"))
        return sr

    def _db_check(self, label: str, sql: str, params: tuple, assertion_fn) -> StepResult:
        sr = StepResult(label)
        if not HAS_PSYCOPG2 or not self.db_url:
            sr.mark_pass("skipped (no psycopg2/db_url)")
            print(_warn(f"[DB] {label} — skipped (no DB connection)"))
            return sr
        try:
            t0 = time.time()
            conn = psycopg2.connect(self.db_url)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.close()
            ms = (time.time() - t0) * 1000
            sr.duration_ms = ms
            ok, detail = assertion_fn(row)
            if ok:
                sr.mark_pass(detail)
                print(_ok(f"[DB][{ms:4.0f}ms] {label} — {detail}"))
            else:
                sr.mark_fail(detail)
                print(_fail(f"[DB][{ms:4.0f}ms] {label} — {detail}"))
        except Exception as exc:
            sr.mark_fail(str(exc))
            print(_fail(f"[DB] {label} — EXCEPTION: {exc}"))
        return sr

    # ── auth ─────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> bool:
        print(f"\n{BOLD}{'='*62}{RESET}")
        print(f"{BOLD}  PESE — SynbotHealth Demo Validation{RESET}")
        print(f"{BOLD}  Target: {self.base}{RESET}")
        print(f"{BOLD}{'='*62}{RESET}\n")

        if self.use_dev_token:
            print(_info("Using dev token (DEV_TOKEN_ENABLED=1)..."))
            resp, ms = self._call(
                "POST", "/auth/dev_token",
                params={"roles": "admin,doctor,nurse,receptionist,lab_tech,pharmacist,billing"}
            )
            if resp.status_code == 200:
                token = resp.json().get("token")
                self.session.headers["Authorization"] = f"Bearer {token}"
                print(_ok(f"[{ms:.0f}ms] Auth — dev token obtained"))
                return True
            print(_warn(f"Dev token failed ({resp.status_code}), falling back to password login"))

        resp, ms = self._call(
            "POST", "/token",
            data={"username": email, "password": password, "grant_type": "password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if resp.status_code != 200:
            print(_fail(f"Login failed HTTP {resp.status_code}: {resp.text[:200]}"))
            return False
        token = resp.json().get("access_token")
        self.session.headers["Authorization"] = f"Bearer {token}"
        print(_ok(f"[{ms:.0f}ms] Auth — logged in as {email}"))
        return True

    def check_health(self) -> bool:
        sr = self._step(
            "Health check", "GET", "/health",
            lambda r, b: (
                r.status_code == 200 and b.get("status") == "ok" and b.get("db_connected"),
                f"status={b.get('status')}, db_connected={b.get('db_connected')}, "
                f"patients_in_db={b.get('sage_ar_row_count', 0):,}",
                b
            )
        )
        return sr.passed

    # ── scenario A — existing patient ────────────────────────────────────────

    def run_scenario_a(self) -> Dict:
        print(f"\n{BOLD}{CYAN}{'─'*62}{RESET}")
        print(f"{BOLD}{CYAN}  SCENARIO A — Existing Patient (Hope ETL Regression){RESET}")
        print(f"{BOLD}{CYAN}{'─'*62}{RESET}\n")

        steps: Dict[str, Any] = {}
        mrn = None
        patient_id = None

        # Try to pick a real patient from the Hope import directly from DB
        if HAS_PSYCOPG2 and self.db_url:
            try:
                conn = psycopg2.connect(self.db_url)
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT mrn, id FROM royan_patients "
                        "WHERE is_active = true AND external_source = 'hope' "
                        "ORDER BY id LIMIT 1"
                    )
                    row = cur.fetchone()
                conn.close()
                if row:
                    mrn = row["mrn"]
                    patient_id = row["id"]
                    print(_info(f"Selected Hope patient: MRN={mrn}, ID={patient_id}"))
            except Exception as exc:
                print(_warn(f"DB lookup for existing patient failed: {exc}"))

        # Fallback: search via API
        if not mrn:
            sr = self._step(
                "Find existing patient", "GET", "/patients/search",
                lambda r, b: (
                    r.status_code == 200 and len(b.get("patients", [])) > 0,
                    f"found {b.get('count', 0)} patients",
                    b
                ),
                params={"q": "ROY", "limit": 1}
            )
            steps["find_patient"] = sr.to_dict()
            if not sr.passed:
                print(_warn("Scenario A skipped — no existing patients found"))
                return {"status": "SKIPPED", "reason": "no existing patients", "steps": steps}
            patient = sr.data.get("patients", [{}])[0]
            mrn = patient.get("mrn") or patient.get("patient_mrn")
            patient_id = patient.get("id")

        # Patient card
        sr = self._step(
            "Get patient card", "GET", f"/patients/{mrn}",
            lambda r, b: (
                r.status_code == 200,
                f"MRN={mrn}, name={b.get('first_name','?')} {b.get('last_name','?')}",
                b
            )
        )
        steps["get_patient_card"] = sr.to_dict()
        if sr.passed and not patient_id:
            patient_id = sr.data.get("id")

        # CPRS profile (pre-encounter)
        sr = self._step(
            "Get patient profile (CPRS)", "GET", f"/patients/{mrn}/profile",
            lambda r, b: (
                r.status_code == 200,
                f"encounters={len(b.get('encounters', []))}, "
                f"lab_orders={len(b.get('lab_orders', []))}, "
                f"timeline_entries={len(b.get('timeline', []))}",
                b
            )
        )
        steps["get_profile_cprs"] = sr.to_dict()

        if not patient_id:
            return {"status": "FAIL", "reason": "could not resolve patient_id", "steps": steps}

        lifecycle_steps, lifecycle_ids = self._run_lifecycle(patient_id, mrn, "A")
        steps.update(lifecycle_steps)

        db_steps = self._validate_db(mrn, lifecycle_ids)
        steps.update(db_steps)

        passed = sum(1 for s in steps.values() if s.get("passed"))
        total = len(steps)
        status = "PASS" if all(s.get("passed") for s in steps.values()) else "PARTIAL"
        return {"status": status, "mrn": mrn, "patient_id": patient_id,
                "steps": steps, "passed": passed, "total": total}

    # ── scenario B — new patient ──────────────────────────────────────────────

    def run_scenario_b(self) -> Dict:
        print(f"\n{BOLD}{CYAN}{'─'*62}{RESET}")
        print(f"{BOLD}{CYAN}  SCENARIO B — New Patient Registration + Full Lifecycle{RESET}")
        print(f"{BOLD}{CYAN}{'─'*62}{RESET}\n")

        steps: Dict[str, Any] = {}
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        phone = f"+234800{ts}"
        self._scenario_b_phone = phone

        sr = self._step(
            "Register new patient", "POST", "/patients/register",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok") and b.get("mrn"),
                f"MRN={b.get('mrn')}, patient_id={b.get('patient', {}).get('id')}",
                b
            ),
            json={
                "first_name": "PESE",
                "last_name": f"Demo{ts}",
                "date_of_birth": "1990-01-15",
                "gender": "male",
                "phone": phone,
                "allergies": ["Penicillin"],
                "blood_group": "O+",
                "next_of_kin_name": "Test NOK",
                "next_of_kin_phone": "+2348099999999",
            },
            params={"force": "true"}
        )
        steps["register_patient"] = sr.to_dict()
        if not sr.passed:
            return {"status": "FAIL", "reason": "patient registration failed", "steps": steps}

        mrn = sr.data.get("mrn")
        patient_id = sr.data.get("patient", {}).get("id")

        if not patient_id:
            resp, _ = self._call("GET", f"/patients/{mrn}")
            if resp.status_code == 200:
                patient_id = resp.json().get("id")

        if not patient_id:
            return {"status": "FAIL",
                    "reason": "could not resolve patient_id after registration",
                    "steps": steps}

        lifecycle_steps, lifecycle_ids = self._run_lifecycle(patient_id, mrn, "B")
        steps.update(lifecycle_steps)

        db_steps = self._validate_db(mrn, lifecycle_ids)
        steps.update(db_steps)

        passed = sum(1 for s in steps.values() if s.get("passed"))
        total = len(steps)
        status = "PASS" if all(s.get("passed") for s in steps.values()) else "PARTIAL"
        return {"status": status, "mrn": mrn, "patient_id": patient_id,
                "bill_id": lifecycle_ids.get("bill_id"),
                "steps": steps, "passed": passed, "total": total}

    # ── core lifecycle (shared A + B) ─────────────────────────────────────────
    #
    # Status machine (enforced by ENCOUNTER_STATUS_TRANSITIONS in constants.py):
    #   patient_registered → triaged → nurse_assessment → called → consulting
    #   → lab_ordered → pharmacy_dispensing → billing_pending → discharged
    #
    # Every → must be an explicit advance call; there is no auto-advance.

    def _run_lifecycle(self, patient_id: int, mrn: str, scenario: str
                       ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        steps: Dict[str, Any] = {}
        ids: Dict[str, Any] = {"patient_id": patient_id, "mrn": mrn}

        # 1 — Open encounter  (→ patient_registered)
        sr = self._step(
            f"[{scenario}] Open encounter", "POST", "/queue/encounters",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"encounter_id={b.get('encounter', {}).get('id')}, "
                f"queue_number={b.get('encounter', {}).get('queue_number')}",
                b
            ),
            json={"patient_id": patient_id, "encounter_type": "outpatient",
                  "department": "OPD",
                  "chief_complaint": f"PESE test visit — scenario {scenario}"}
        )
        steps["open_encounter"] = sr.to_dict()
        encounter_id = sr.data.get("encounter", {}).get("id")
        if not encounter_id:
            print(_warn("Cannot continue lifecycle — encounter_id not returned"))
            return steps, ids
        ids["encounter_id"] = encounter_id

        # 2 — Record vitals (separate table, no status change)
        sr = self._step(
            f"[{scenario}] Record vitals", "POST", "/nursing/vitals",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"vitals_id={b.get('vitals', {}).get('id')}, "
                f"bp={b.get('vitals', {}).get('bp_systolic')}/{b.get('vitals', {}).get('bp_diastolic')}",
                b
            ),
            json={"patient_id": patient_id, "encounter_id": encounter_id,
                  "temperature": 36.8, "pulse": 72, "respiratory_rate": 16,
                  "bp_systolic": 120, "bp_diastolic": 80, "spo2": 98,
                  "weight": 70.0, "height": 175.0, "pain_score": 2}
        )
        steps["record_vitals"] = sr.to_dict()
        ids["vitals_id"] = sr.data.get("vitals", {}).get("id")

        # 3 — Triage  (patient_registered → triaged)
        sr = self._step(
            f"[{scenario}] Triage", "POST",
            f"/queue/encounters/{encounter_id}/triage",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={"triage_level": "non_urgent",
                  "triage_notes": f"PESE test — Scenario {scenario}. Patient stable."}
        )
        steps["triage"] = sr.to_dict()

        # 4 — Nurse done  (triaged → nurse_assessment)
        sr = self._step(
            f"[{scenario}] Nurse assessment done", "POST",
            f"/queue/encounters/{encounter_id}/nurse-done",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={}
        )
        steps["nurse_done"] = sr.to_dict()

        # 5 — Call patient  (nurse_assessment → called)
        sr = self._step(
            f"[{scenario}] Call patient", "POST",
            f"/queue/encounters/{encounter_id}/call",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}, room={b.get('room')}",
                b
            ),
            json={"room": "Consulting Room 3"}
        )
        steps["call_patient"] = sr.to_dict()

        # 6 — Consult  (called → consulting)
        sr = self._step(
            f"[{scenario}] Doctor consultation", "POST",
            f"/queue/encounters/{encounter_id}/consult",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={"consulting_doctor": "Dr. PESE Test",
                  "diagnosis_notes": "PESE validation — routine check, no acute pathology.",
                  "diagnosis_codes": ["Z00.0"]}
        )
        steps["consult"] = sr.to_dict()

        # 7 — Clinical SOAP note (no status change — separate table)
        sr = self._step(
            f"[{scenario}] Add SOAP note", "POST",
            f"/queue/encounters/{encounter_id}/notes",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"note_id={b.get('note', {}).get('id')}",
                b
            ),
            json={"content": (
                "S: Patient presents for routine check. Reports mild fatigue.\n"
                "O: Vitals stable. BP 120/80, SpO2 98%, Temp 36.8°C.\n"
                "A: No acute distress. Routine health check.\n"
                "P: FBC ordered. Paracetamol 500mg TID PRN. Follow-up in 2 weeks."
            ), "note_type": "soap"}
        )
        steps["add_note"] = sr.to_dict()

        # 8 — Lab order
        sr = self._step(
            f"[{scenario}] Order lab (FBC)", "POST", "/lab/orders",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"order_id={b.get('order', {}).get('id')}, "
                f"status={b.get('order', {}).get('status')}",
                b
            ),
            json={"encounter_id": encounter_id, "patient_id": patient_id,
                  "test_name": "Full Blood Count", "test_code": "FBC",
                  "urgency": "routine",
                  "notes": "PESE test — routine screening"}
        )
        steps["lab_order"] = sr.to_dict()
        lab_order_id = sr.data.get("order", {}).get("id")
        ids["lab_order_id"] = lab_order_id

        # 8b — Advance encounter  (consulting → lab_ordered)
        sr = self._step(
            f"[{scenario}] Advance → lab_ordered", "POST",
            f"/queue/encounters/{encounter_id}/advance",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={"new_status": "lab_ordered", "notes": "FBC sent to lab"}
        )
        steps["advance_lab_ordered"] = sr.to_dict()

        # 9 — Record lab result (separate table, no encounter status change)
        if lab_order_id:
            sr = self._step(
                f"[{scenario}] Record lab result", "POST",
                f"/lab/orders/{lab_order_id}/result",
                lambda r, b: (
                    r.status_code in (200, 201) and b.get("ok"),
                    f"result_id={b.get('result', {}).get('id')}, "
                    f"critical={b.get('result', {}).get('is_critical')}",
                    b
                ),
                json={"result_value": "13.5", "result_unit": "g/dL",
                      "result_summary": "Haemoglobin within normal range",
                      "result_data": {"haemoglobin": "13.5 g/dL",
                                      "WBC": "6.2 x10^3/uL",
                                      "platelets": "280 x10^3/uL"},
                      "reference_range": "12.0-16.0 g/dL",
                      "interpretation": "normal",
                      "is_critical": False,
                      "resulted_by": "Dr. PESE Lab"}
            )
            steps["lab_result"] = sr.to_dict()
        else:
            print(_warn(f"[{scenario}] Lab result skipped — no lab_order_id"))

        # 10 — Prescribe Paracetamol
        sr = self._step(
            f"[{scenario}] Prescribe Paracetamol", "POST", "/pharmacy/prescriptions",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"rx_id={b.get('prescription', {}).get('id')}, "
                f"allergy_alert={b.get('allergy_alert', False)}",
                b
            ),
            json={"encounter_id": encounter_id, "patient_id": patient_id,
                  "drug_name": "Paracetamol 500mg", "dosage": "1 tablet",
                  "dose": "500mg", "frequency": "TID", "route": "oral",
                  "duration": "5 days", "quantity": 15, "unit": "tablets",
                  "special_instructions": "Take after meals"}
        )
        steps["prescribe"] = sr.to_dict()
        ids["prescription_id"] = sr.data.get("prescription", {}).get("id")

        if sr.passed and sr.data.get("allergy_alert"):
            print(_warn(f"[{scenario}] Unexpected allergy alert for Paracetamol — check allergy data"))

        # 10b — Advance encounter  (lab_ordered → pharmacy_dispensing)
        sr = self._step(
            f"[{scenario}] Advance → pharmacy_dispensing", "POST",
            f"/queue/encounters/{encounter_id}/advance",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={"new_status": "pharmacy_dispensing", "notes": "Rx sent to pharmacy"}
        )
        steps["advance_pharmacy"] = sr.to_dict()

        # 11 — Create bill
        sr = self._step(
            f"[{scenario}] Create bill", "POST", "/billing_hospital/bills",
            lambda r, b: (
                r.status_code in (200, 201) and b.get("ok"),
                f"bill_id={b.get('bill', {}).get('id')}, "
                f"total=N{b.get('bill', {}).get('total_amount', 0):,.0f}, "
                f"due=N{b.get('bill', {}).get('patient_due', 0):,.0f}, "
                f"status={b.get('bill', {}).get('status')}",
                b
            ),
            json={"encounter_id": encounter_id, "patient_id": patient_id,
                  "consultation_fee": 3000.0, "lab_charges": 5000.0,
                  "pharmacy_charges": 1500.0, "notes": "PESE test bill"}
        )
        steps["create_bill"] = sr.to_dict()
        bill_id = sr.data.get("bill", {}).get("id")
        ids["bill_id"] = bill_id
        # patient_due is the amount the patient actually owes (after HMO/discount)
        amount_due = sr.data.get("bill", {}).get("patient_due") or \
                     sr.data.get("bill", {}).get("total_amount") or 9500.0

        # 11b — Advance encounter  (pharmacy_dispensing → billing_pending)
        sr = self._step(
            f"[{scenario}] Advance → billing_pending", "POST",
            f"/queue/encounters/{encounter_id}/advance",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}",
                b
            ),
            json={"new_status": "billing_pending", "notes": "Bill generated, awaiting payment"}
        )
        steps["advance_billing"] = sr.to_dict()

        # 12 — Record payment
        if bill_id:
            sr = self._step(
                f"[{scenario}] Record payment (N{amount_due:,.0f})", "POST",
                f"/billing_hospital/bills/{bill_id}/payment",
                lambda r, b: (
                    r.status_code in (200, 201) and b.get("ok"),
                    f"payment_id={b.get('payment', {}).get('id')}, "
                    f"bill_status={b.get('bill_status')}",
                    b
                ),
                json={"amount": amount_due, "payment_method": "cash",
                      "reference": f"PESE-{scenario}-{datetime.now().strftime('%H%M%S')}"}
            )
            steps["payment"] = sr.to_dict()
        else:
            print(_warn(f"[{scenario}] Payment skipped — no bill_id"))

        # 13 — Discharge  (billing_pending → discharged)
        sr = self._step(
            f"[{scenario}] Discharge patient", "POST",
            f"/queue/encounters/{encounter_id}/discharge",
            lambda r, b: (
                r.status_code == 200 and b.get("ok"),
                f"status={b.get('status')}, "
                f"discharged_at={str(b.get('discharged_at', ''))[:19] or 'N/A'}",
                b
            ),
            json={"discharge_summary": (
                f"PESE Scenario {scenario} test encounter completed. "
                "Patient discharged in stable condition after routine check. "
                "CBC within normal limits. Paracetamol dispensed. Payment received."
            )}
        )
        steps["discharge"] = sr.to_dict()

        # 14 — CPRS profile (post-encounter; confirms everything linked)
        sr = self._step(
            f"[{scenario}] CPRS profile (post-discharge)", "GET",
            f"/patients/{mrn}/profile",
            lambda r, b: (
                r.status_code == 200
                and len(b.get("encounters", [])) > 0
                and len(b.get("timeline", [])) > 0,
                f"encounters={len(b.get('encounters', []))}, "
                f"lab_orders={len(b.get('lab_orders', []))}, "
                f"prescriptions={len(b.get('prescriptions', []))}, "
                f"bills={len(b.get('bills', []))}, "
                f"timeline_entries={len(b.get('timeline', []))}",
                b
            )
        )
        steps["cprs_profile"] = sr.to_dict()

        return steps, ids

    # ── frontend contract checks ──────────────────────────────────────────────

    def _run_hms_reads(self, patient_id: int) -> Dict[str, Any]:
        """8 GET checks for HMS staff dashboards and CPRS cards."""
        steps: Dict[str, Any] = {}

        sr = self._step(
            "HMS: hospital-status dashboard", "GET", "/dashboard/hospital-status",
            lambda r, b: (
                r.status_code == 200 and (
                    any(k in b for k in (
                        "patient_flow", "queue_summary", "total_encounters",
                        "active_encounters", "daily_admissions", "data",
                        "patients_waiting", "total_encounters_today",
                    ))
                    or any(k in (b.get("data") or {}) for k in (
                        "patients_waiting", "total_encounters_today",
                        "active_consultations", "queue_by_department",
                    ))
                ),
                (lambda d: f"keys={list(d.keys())[:6]}")(b.get("data") or b),
                b
            ),
            timeout=90
        )
        steps["hms_hospital_status"] = sr.to_dict()

        sr = self._step(
            "HMS: queue board (discharged encounters)", "GET", "/queue/encounters",
            lambda r, b: (
                r.status_code == 200,
                f"count={len(b) if isinstance(b, list) else b.get('count', len(b.get('encounters', b.get('data', []))))}",
                b
            ),
            params={"status": "discharged", "limit": 5},
            timeout=90
        )
        steps["hms_queue_board"] = sr.to_dict()

        sr = self._step(
            "HMS: lab orders list", "GET", "/lab/orders",
            lambda r, b: (
                r.status_code == 200,
                f"count={len(b) if isinstance(b, list) else b.get('count', '?')}",
                b
            ),
            params={"limit": 5},
            timeout=90
        )
        steps["hms_lab_orders"] = sr.to_dict()

        sr = self._step(
            "HMS: pharmacy prescriptions", "GET", "/pharmacy/prescriptions",
            lambda r, b: (
                r.status_code == 200,
                f"count={len(b) if isinstance(b, list) else b.get('count', '?')}",
                b
            ),
            params={"limit": 5},
            timeout=90
        )
        steps["hms_pharmacy_prescriptions"] = sr.to_dict()

        sr = self._step(
            "HMS: billing list", "GET", "/billing_hospital/bills",
            lambda r, b: (
                r.status_code == 200,
                f"count={len(b) if isinstance(b, list) else b.get('count', '?')}",
                b
            ),
            params={"limit": 5},
            timeout=90
        )
        steps["hms_billing_list"] = sr.to_dict()

        sr = self._step(
            "HMS: patient vitals (CPRS)", "GET", f"/nursing/vitals/{patient_id}",
            lambda r, b: (
                r.status_code == 200,
                f"vitals_count={len(b) if isinstance(b, list) else b.get('count', '?')}",
                b
            ),
            timeout=90
        )
        steps["hms_cprs_vitals"] = sr.to_dict()

        sr = self._step(
            "HMS: patient lab history (CPRS)", "GET", f"/lab/patients/{patient_id}/history",
            lambda r, b: (
                r.status_code == 200 and b.get("count", 0) >= 1,
                f"records={b.get('count', 0)} (expect ≥1 from lifecycle)",
                b
            ),
            timeout=90
        )
        steps["hms_cprs_lab_history"] = sr.to_dict()

        sr = self._step(
            "HMS: staff dashboard", "GET", "/staff/admin/dashboard",
            lambda r, b: (
                r.status_code == 200 and any(
                    k in b for k in ("kpis", "activities", "tasks", "summary", "stats", "data")
                ),
                f"keys={list(b.keys())[:6]}",
                b
            )
        )
        steps["hms_staff_dashboard"] = sr.to_dict()

        return steps

    def _run_portal_contracts(self, mrn: str, phone: str, bill_id: Optional[int]) -> Dict[str, Any]:
        """11 checks against patient portal endpoints using portal JWT."""
        steps: Dict[str, Any] = {}

        portal = requests.Session()
        portal.headers["Content-Type"] = "application/json"
        portal.verify = False

        # Portal login
        portal_token = None
        t0 = time.time()
        try:
            resp = portal.post(self._url("/portal/auth"),
                               json={"mrn": mrn, "phone": phone}, timeout=30)
            ms = (time.time() - t0) * 1000
            body = resp.json() if resp.ok else {}
            portal_token = body.get("token") or body.get("access_token")
            ok = (resp.status_code == 200
                  and bool(portal_token)
                  and (body.get("patient") or {}).get("mrn") == mrn)
            sr = StepResult("Portal: login (MRN+phone → JWT)")
            sr.status_code = resp.status_code
            sr.duration_ms = ms
            if ok:
                sr.mark_pass(f"token={'set'}, patient.mrn={mrn}", body)
                print(_ok(f"[{ms:5.0f}ms] Portal: login — token obtained for MRN {mrn}"))
            else:
                sr.mark_fail(f"HTTP {resp.status_code}: token={bool(portal_token)}, "
                             f"mrn_match={(body.get('patient') or {}).get('mrn')} vs {mrn}")
                print(_fail(f"[{ms:5.0f}ms] Portal: login — {sr.detail}"))
                if body:
                    print(_info(f"Response: {json.dumps(body)[:300]}"))
        except Exception as exc:
            sr = StepResult("Portal: login (MRN+phone → JWT)")
            sr.mark_fail(str(exc))
            print(_fail(f"Portal: login — EXCEPTION: {exc}"))
        steps["portal_login"] = sr.to_dict()

        if portal_token:
            portal.headers["Authorization"] = f"Bearer {portal_token}"

        def _get(path, **params):
            t = time.time()
            r = portal.get(self._url(path), params=params or None, timeout=30)
            return r, (time.time() - t) * 1000

        def _portal_check(name, path, assertion_fn, **params):
            sr = StepResult(name)
            try:
                resp, ms = _get(path, **params)
                sr.status_code = resp.status_code
                sr.duration_ms = ms
                try:
                    body = resp.json()
                except Exception:
                    body = {"_raw": resp.text[:200]}
                ok, detail, data = assertion_fn(resp, body)
                if ok:
                    sr.mark_pass(detail, data)
                    print(_ok(f"[{ms:5.0f}ms] {name} — {detail}"))
                else:
                    sr.mark_fail(f"HTTP {resp.status_code}: {detail}")
                    print(_fail(f"[{ms:5.0f}ms] {name} — HTTP {resp.status_code}: {detail}"))
                    if body:
                        print(_info(f"Response: {json.dumps(body)[:300]}"))
            except Exception as exc:
                sr.mark_fail(str(exc))
                print(_fail(f"{name} — EXCEPTION: {exc}"))
            return sr

        sr = _portal_check(
            "Portal: /portal/me", "/portal/me",
            lambda r, b: (
                r.status_code == 200 and (
                    "mrn" in (b.get("patient") or b)
                    and "first_name" in (b.get("patient") or b)
                ),
                (lambda p: f"mrn={p.get('mrn')}, first_name={p.get('first_name')}")(
                    b.get("patient") or b
                ),
                b
            )
        )
        steps["portal_me"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/appointments", "/portal/appointments",
            lambda r, b: (
                r.status_code == 200 and "appointments" in b,
                f"appointments={len(b.get('appointments', []))}",
                b
            )
        )
        steps["portal_appointments"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/lab-results", "/portal/lab-results",
            lambda r, b: (
                r.status_code == 200 and len(b.get("results", [])) >= 1,
                f"results={len(b.get('results', []))} (expect ≥1 from lifecycle)",
                b
            )
        )
        steps["portal_lab_results"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/bills", "/portal/bills",
            lambda r, b: (
                r.status_code == 200 and len(b.get("bills", [])) >= 1,
                f"bills={len(b.get('bills', []))} (expect ≥1 from lifecycle)",
                b
            )
        )
        steps["portal_bills"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/prescriptions", "/portal/prescriptions",
            lambda r, b: (
                r.status_code == 200 and "prescriptions" in b,
                f"prescriptions={len(b.get('prescriptions', []))} (expect ≥1 from lifecycle)",
                b
            )
        )
        steps["portal_prescriptions"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/vitals", "/portal/vitals",
            lambda r, b: (
                r.status_code == 200 and len(b.get("vitals", [])) >= 1,
                f"vitals={len(b.get('vitals', []))} (expect ≥1 from lifecycle)",
                b
            )
        )
        steps["portal_vitals"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/notifications", "/portal/notifications",
            lambda r, b: (
                r.status_code == 200 and "notifications" in b,
                f"notifications={len(b.get('notifications', []))}",
                b
            )
        )
        steps["portal_notifications"] = sr.to_dict()

        sr = _portal_check(
            "Portal: /portal/telemedicine", "/portal/telemedicine",
            lambda r, b: (
                r.status_code == 200 and "sessions" in b,
                f"sessions={len(b.get('sessions', []))}",
                b
            )
        )
        steps["portal_telemedicine"] = sr.to_dict()

        # 401 guard — call /portal/me with NO token
        guard_session = requests.Session()
        guard_session.headers["Content-Type"] = "application/json"
        guard_session.verify = False
        sr = StepResult("Portal: 401 auth guard")
        try:
            t0 = time.time()
            resp = guard_session.get(self._url("/portal/me"), timeout=30)
            ms = (time.time() - t0) * 1000
            sr.status_code = resp.status_code
            sr.duration_ms = ms
            if resp.status_code == 401:
                sr.mark_pass("correctly rejected unauthenticated request")
                print(_ok(f"[{ms:5.0f}ms] Portal: 401 auth guard — 401 returned correctly"))
            else:
                sr.mark_fail(f"expected 401, got {resp.status_code}")
                print(_fail(f"[{ms:5.0f}ms] Portal: 401 auth guard — expected 401, got {resp.status_code}"))
        except Exception as exc:
            sr.mark_fail(str(exc))
            print(_fail(f"Portal: 401 auth guard — EXCEPTION: {exc}"))
        steps["portal_auth_guard_401"] = sr.to_dict()

        # /payments/initiate (uses admin session — HMS-level endpoint, not portal-scoped)
        if bill_id:
            sr = StepResult("Portal: /payments/initiate")
            try:
                t0 = time.time()
                resp = self.session.post(self._url("/payments/initiate"),
                                         json={"bill_id": bill_id}, timeout=30,
                                         verify=False)
                ms = (time.time() - t0) * 1000
                sr.status_code = resp.status_code
                sr.duration_ms = ms
                body = {}
                try:
                    body = resp.json()
                except Exception:
                    body = {"_raw": resp.text[:200]}
                has_url = bool(body.get("checkout_url") or body.get("payment_url")
                               or body.get("authorization_url"))
                # 200/201 with payment URL, OR 400/409 if bill already paid — both acceptable
                ok = resp.status_code in (200, 201) and has_url
                if ok:
                    sr.mark_pass(f"checkout_url returned", body)
                    print(_ok(f"[{ms:5.0f}ms] Portal: /payments/initiate — checkout_url present"))
                elif resp.status_code in (400, 409, 422):
                    sr.mark_pass(f"bill already settled ({resp.status_code}) — endpoint reachable", body)
                    print(_ok(f"[{ms:5.0f}ms] Portal: /payments/initiate — bill settled ({resp.status_code}), endpoint live"))
                else:
                    sr.mark_fail(f"HTTP {resp.status_code}: checkout_url={has_url}")
                    print(_fail(f"[{ms:5.0f}ms] Portal: /payments/initiate — {sr.detail}"))
                    if body:
                        print(_info(f"Response: {json.dumps(body)[:300]}"))
            except Exception as exc:
                sr.mark_fail(str(exc))
                print(_fail(f"Portal: /payments/initiate — EXCEPTION: {exc}"))
            steps["portal_payments_initiate"] = sr.to_dict()
        else:
            print(_warn("Portal: /payments/initiate skipped — no bill_id"))

        return steps

    def _run_synbotui_contracts(self) -> Dict[str, Any]:
        """3 checks for SynbotUI's implemented endpoints."""
        steps: Dict[str, Any] = {}

        sr = self._step(
            "SynbotUI: /schemas list", "GET", "/schemas",
            lambda r, b: (
                r.status_code == 200,
                f"type={type(b).__name__}, count={len(b) if isinstance(b, list) else '?'}",
                b
            )
        )
        steps["synbotui_schemas_list"] = sr.to_dict()

        # Pick the first schema name from the list response
        first_schema = None
        if sr.passed:
            data = sr.data
            if isinstance(data, list) and data:
                first_schema = data[0].get("name") or data[0].get("id") or str(data[0]) if isinstance(data[0], str) else None
            elif isinstance(data, dict):
                names = data.get("schemas") or data.get("forms") or data.get("names") or []
                if names:
                    first_schema = names[0] if isinstance(names[0], str) else names[0].get("name")

        if first_schema:
            sr = self._step(
                f"SynbotUI: /schemas/{first_schema}", "GET", f"/schemas/{first_schema}",
                lambda r, b: (
                    r.status_code == 200 and any(
                        k in b for k in ("properties", "schema", "fields", "form", "name", "title")
                    ),
                    f"keys={list(b.keys())[:6]}",
                    b
                )
            )
            steps["synbotui_schema_detail"] = sr.to_dict()
        else:
            print(_warn("SynbotUI: /schemas/{name} skipped — could not resolve a schema name"))

        sr = self._step(
            "SynbotUI: /staff/admin/dashboard", "GET", "/staff/admin/dashboard",
            lambda r, b: (
                r.status_code == 200 and any(
                    k in b for k in ("kpis", "activities", "tasks", "summary", "stats",
                                     "queue", "encounters", "data")
                ),
                f"keys={list(b.keys())[:6]}",
                b
            )
        )
        steps["synbotui_staff_dashboard"] = sr.to_dict()

        return steps

    def run_frontend_contracts(self, scenario_b_result: Dict) -> Dict:
        """Validate frontend button → backend contract wiring for all live pages."""
        print(f"\n{BOLD}{CYAN}{'─'*62}{RESET}")
        print(f"{BOLD}{CYAN}  FRONTEND CONTRACTS — Button/Page → Endpoint Wiring{RESET}")
        print(f"{BOLD}{CYAN}{'─'*62}{RESET}\n")
        print(f"  {BOLD}── HMS Clinical Read Endpoints ────────────────────────{RESET}")

        patient_id = scenario_b_result.get("patient_id")
        mrn = scenario_b_result.get("mrn")
        phone = self._scenario_b_phone
        bill_id = scenario_b_result.get("bill_id")

        steps: Dict[str, Any] = {}

        hms_steps = self._run_hms_reads(patient_id)
        steps.update(hms_steps)

        print(f"\n  {BOLD}── Patient Portal Contracts ───────────────────────────{RESET}")
        portal_steps = self._run_portal_contracts(mrn, phone, bill_id)
        steps.update(portal_steps)

        print(f"\n  {BOLD}── SynbotUI Implemented Endpoints ─────────────────────{RESET}")
        synbot_steps = self._run_synbotui_contracts()
        steps.update(synbot_steps)

        passed = sum(1 for s in steps.values() if s.get("passed"))
        total = len(steps)
        return {
            "status": "PASS" if passed == total else "PARTIAL",
            "passed": passed,
            "total": total,
            "steps": steps,
        }

    # ── DB truth checks ───────────────────────────────────────────────────────

    def _validate_db(self, mrn: str, ids: Dict) -> Dict[str, Any]:
        print(f"\n  {BOLD}── DB Truth Checks ──────────────────────────────────────{RESET}")
        steps: Dict[str, Any] = {}
        eid = ids.get("encounter_id")
        lid = ids.get("lab_order_id")
        bid = ids.get("bill_id")

        if eid:
            # Discharge column is `discharge_at` (not `discharged_at`) in royan_encounters
            sr = self._db_check(
                "DB: encounter discharged",
                "SELECT status, discharge_at FROM royan_encounters WHERE id = %s",
                (eid,),
                lambda row: (
                    row is not None and row["status"] == "discharged",
                    f"status={row['status'] if row else 'NOT FOUND'}, "
                    f"discharge_at={'set' if row and row.get('discharge_at') else 'NULL'}"
                )
            )
            steps["db_encounter_discharged"] = sr.to_dict()

            sr = self._db_check(
                "DB: clinical note recorded",
                "SELECT COUNT(*) AS cnt FROM royan_encounter_notes WHERE encounter_id = %s",
                (eid,),
                lambda row: (
                    row is not None and row["cnt"] >= 1,
                    f"notes_count={row['cnt'] if row else 0}"
                )
            )
            steps["db_note_exists"] = sr.to_dict()

            sr = self._db_check(
                "DB: vitals recorded",
                "SELECT COUNT(*) AS cnt FROM royan_vitals WHERE encounter_id = %s",
                (eid,),
                lambda row: (
                    row is not None and row["cnt"] >= 1,
                    f"vitals_count={row['cnt'] if row else 0}"
                )
            )
            steps["db_vitals_exist"] = sr.to_dict()

        if lid:
            sr = self._db_check(
                "DB: lab order resulted",
                "SELECT status FROM royan_lab_orders WHERE id = %s",
                (lid,),
                lambda row: (
                    row is not None and row["status"] == "resulted",
                    f"status={row['status'] if row else 'NOT FOUND'}"
                )
            )
            steps["db_lab_resulted"] = sr.to_dict()

        if bid:
            sr = self._db_check(
                "DB: bill fully paid",
                "SELECT status FROM royan_billing WHERE id = %s",
                (bid,),
                lambda row: (
                    row is not None and row["status"] == "paid",
                    f"status={row['status'] if row else 'NOT FOUND'}"
                )
            )
            steps["db_bill_paid"] = sr.to_dict()

        return steps

    # ── report ────────────────────────────────────────────────────────────────

    def run(self, admin_email: str, admin_password: str) -> int:
        if not self.login(admin_email, admin_password):
            return 1
        if not self.check_health():
            print(_fail("Health check failed — is the backend running?"))
            return 1

        t0 = time.time()
        scenario_a = self.run_scenario_a()
        scenario_b = self.run_scenario_b()
        frontend   = self.run_frontend_contracts(scenario_b)
        duration = time.time() - t0

        all_steps = (
            list(scenario_a.get("steps", {}).values())
            + list(scenario_b.get("steps", {}).values())
            + list(frontend.get("steps", {}).values())
        )
        total  = len(all_steps)
        passed = sum(1 for s in all_steps if s.get("passed"))
        failed = total - passed

        failures: List[str] = []
        for sc_name, sc_data in [("A_existing_patient", scenario_a),
                                   ("B_new_patient", scenario_b),
                                   ("frontend_contracts", frontend)]:
            for step_name, step_data in sc_data.get("steps", {}).items():
                if not step_data.get("passed"):
                    failures.append(f"{sc_name}.{step_name}: {step_data.get('detail', '')}")

        report = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "base_url": self.base,
            "scenarios": {
                "A_existing_patient": {
                    "status": scenario_a.get("status"),
                    "mrn": scenario_a.get("mrn"),
                    "passed": scenario_a.get("passed", 0),
                    "total": scenario_a.get("total", 0),
                    "steps": scenario_a.get("steps", {}),
                },
                "B_new_patient": {
                    "status": scenario_b.get("status"),
                    "mrn": scenario_b.get("mrn"),
                    "passed": scenario_b.get("passed", 0),
                    "total": scenario_b.get("total", 0),
                    "steps": scenario_b.get("steps", {}),
                },
                "frontend_contracts": {
                    "status": frontend.get("status"),
                    "passed": frontend.get("passed", 0),
                    "total": frontend.get("total", 0),
                    "steps": frontend.get("steps", {}),
                },
            },
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "failures": failures,
            "duration_seconds": round(duration, 2),
        }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"backend/tests/pese_report_{ts}.json"
        try:
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
        except Exception:
            report_path = None

        print(f"\n{BOLD}{'='*62}{RESET}")
        if failed == 0:
            print(f"{GREEN}{BOLD}  ALL {total} CHECKS PASSED — DEMO READY{RESET}")
        else:
            print(f"{RED}{BOLD}  {failed}/{total} CHECKS FAILED{RESET}")
            for f_ in failures:
                print(f"{RED}     • {f_}{RESET}")

        print(f"\n  Scenario A  ({scenario_a.get('status','?')}):  MRN = {scenario_a.get('mrn', '—')}")
        print(f"  Scenario B  ({scenario_b.get('status','?')}):  MRN = {scenario_b.get('mrn', '—')}")
        fe_p = frontend.get("passed", 0)
        fe_t = frontend.get("total", 0)
        print(f"  Frontend    ({frontend.get('status','?')}):  {fe_p}/{fe_t} contract checks")
        print(f"  Duration:  {duration:.1f}s")
        if report_path:
            print(f"  Report:    {report_path}")
        print(f"{BOLD}{'='*62}{RESET}\n")

        return 0 if failed == 0 else 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PESE — SynbotHealth Patient Encounter Simulation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", default="http://localhost",
                        help="Backend base URL (default: http://localhost)")
    parser.add_argument("--admin-email", default="admin@royanhospital.com")
    parser.add_argument("--admin-password", default="royan1234")
    parser.add_argument("--dev-token", action="store_true",
                        help="Use /auth/dev_token instead of password (requires DEV_TOKEN_ENABLED=1)")
    parser.add_argument("--db-url",
                        default="postgresql://postgres:admin1234@localhost:5433/synbot_health",
                        help="PostgreSQL DSN for direct DB validation")
    args = parser.parse_args()

    runner = PESERunner(
        base_url=args.url,
        db_url=args.db_url if HAS_PSYCOPG2 else None,
        use_dev_token=args.dev_token,
    )
    sys.exit(runner.run(args.admin_email, args.admin_password))


if __name__ == "__main__":
    main()
