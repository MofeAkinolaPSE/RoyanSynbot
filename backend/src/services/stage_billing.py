"""Stage billing: the patient pays before each service (Royan finance meeting, 10 Oct 2026).

    1. Front desk opens the encounter      -> bill: registration (new patients) + consultation fee
    2. Doctor finishes / sends to cashier  -> bill: everything ordered and not yet billed (lab, drugs, procedures);
                                              scans on a separate Scancare bill (Scancare keeps its own books)
    3. Cashier records payment (full or part) and the departments serve the patient.
    Admitted patients keep their running bill; HMO patients are billed the same way and claimed.

Pay first (royan_billing_settings.pay_first = 'private_outpatient'): lab sample collection, scans and dispensing
check `clearance()` for a private outpatient - the order must be on a bill that is paid, or part-paid and released
by the cashier, or released by a supervisor with a reason. HMO, staff-scheme and admitted patients are not held.

Every bill is created through billing_hospital.create_coverage_bill, so HMO cover, the Roy Books invoice and the
patient's own ledger follow automatically.
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin.db import q, q1, tx

log = logging.getLogger("stage_billing")

ORDER_SOURCES = ("lab_order", "radiology_order", "prescription")
SCANCARE_SOURCES = ("radiology_order",)


def _setting(conn, key: str) -> Optional[str]:
    r = q1(conn, "SELECT value FROM royan_billing_settings WHERE key=%s", (key,))
    return r["value"] if r else None


def _service(conn, service_id: Any) -> Optional[Dict[str, Any]]:
    if not service_id:
        return None
    return q1(conn, "SELECT id, name, base_price, category, service_code FROM royan_service_catalog WHERE id=%s", (service_id,))


def is_new_patient(conn, patient_id: int, encounter_id: int) -> bool:
    """New = never registered before: no earlier encounter (Hope's or ours) and no registration already billed."""
    if q1(conn, "SELECT 1 FROM royan_bill_items WHERE source='registration' AND source_id=%s", (str(patient_id),)):
        return False
    return not q1(conn, "SELECT 1 FROM royan_encounters WHERE patient_id=%s AND id<>%s LIMIT 1", (patient_id, encounter_id))


def consultation_quote(conn, encounter: Dict[str, Any], specialty: Optional[str] = None, kind: Optional[str] = None) -> Dict[str, Any]:
    """Which consultation item and fee applies: the doctor's own fee if set, else the specialty's tariff (from the
    doctor, the chosen specialty, or the clinic / department). First visit unless the patient saw the same specialty
    within its follow-up window."""
    doc_fee = q1(conn, "SELECT * FROM royan_doctor_consultation_fees WHERE doctor_id=%s",
                 (str(encounter["doctor_id"]),)) if encounter.get("doctor_id") else None
    tariff = None
    if specialty:
        tariff = q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE is_active AND (specialty=%s OR id::text=%s)", (specialty, specialty))
    if not tariff and doc_fee and doc_fee.get("tariff_id"):
        tariff = q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE id=%s", (doc_fee["tariff_id"],))
    if not tariff and encounter.get("doctor_id"):
        tariff = q1(conn, """SELECT t.* FROM royan_staff s JOIN royan_consultation_tariffs t ON t.is_active
                             AND lower(t.specialty)=lower(s.specialty) WHERE s.id=%s""", (str(encounter["doctor_id"]),))
    if not tariff:
        dept = q1(conn, "SELECT code FROM royan_departments WHERE upper(name)=upper(%s) OR upper(code)=upper(%s)",
                  (encounter.get("department") or "", encounter.get("department") or ""))
        tariff = q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE is_active AND department_code=%s",
                    ((dept or {}).get("code") or "OPD",))
    if not tariff:
        tariff = q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE specialty='General Practice'")
    if not kind:
        recent = q1(conn, """SELECT 1 FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                             WHERE i.patient_id=%s AND i.source='consultation' AND i.service_id = ANY(%s)
                               AND b.status <> 'void' AND i.source_id NOT LIKE '%%:void:%%'
                               AND b.billed_at > now() - (%s || ' days')::interval AND i.source_id <> %s LIMIT 1""",
                    (encounter["patient_id"], [x for x in (tariff.get("initial_service_id"), tariff.get("follow_up_service_id")) if x],
                     str(tariff.get("follow_up_days") or 30), str(encounter["id"])))
        kind = "follow_up" if recent else "initial"
    svc = _service(conn, tariff.get({"initial": "initial_service_id", "follow_up": "follow_up_service_id",
                                     "review": "review_service_id"}.get(kind, "initial_service_id"))) or _service(conn, tariff.get("initial_service_id"))
    price = Decimal(str((svc or {}).get("base_price") or 0))
    if doc_fee:
        own = doc_fee.get("follow_up_fee") if kind == "follow_up" else doc_fee.get("initial_fee")
        if own is not None:
            price = Decimal(str(own))
    label = {"initial": "consultation", "follow_up": "follow-up consultation", "review": "result review"}.get(kind, "consultation")
    return {"tariff_id": tariff.get("id"), "specialty": tariff.get("specialty"), "kind": kind,
            "service_id": (svc or {}).get("id"), "service_code": (svc or {}).get("service_code"),
            "description": (svc or {}).get("name") or f"{tariff.get('specialty')} {label}", "unit_price": float(price),
            "doctor_fee": doc_fee is not None}


def front_desk_items(conn, encounter: Dict[str, Any], specialty: Optional[str] = None, kind: Optional[str] = None,
                     include_registration: Optional[bool] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    new = is_new_patient(conn, encounter["patient_id"], encounter["id"]) if include_registration is None else include_registration
    if new:
        reg = _service(conn, _setting(conn, "registration_service_id"))
        if reg:
            items.append({"service_id": reg["id"], "service_code": reg["service_code"], "description": reg["name"],
                          "category": "misc", "quantity": 1, "unit_price": float(reg["base_price"]),
                          "source": "registration", "source_id": str(encounter["patient_id"])})
    if not q1(conn, "SELECT 1 FROM royan_bill_items WHERE source='consultation' AND source_id=%s", (str(encounter["id"]),)):
        c = consultation_quote(conn, encounter, specialty, kind)
        items.append({"service_id": c["service_id"], "service_code": c["service_code"], "description": c["description"],
                      "category": "consultation", "quantity": 1, "unit_price": c["unit_price"],
                      "source": "consultation", "source_id": str(encounter["id"])})
    return items


def _drug_price(conn, formulary_id: Any, drug_name: str) -> float:
    r = None
    if formulary_id:
        r = q1(conn, """SELECT COALESCE(NULLIF(mrp,0), NULLIF(sale_price,0)) p FROM royan_pharmacy_item_rates
                        WHERE formulary_id=%s AND is_active AND COALESCE(NULLIF(mrp,0), NULLIF(sale_price,0)) IS NOT NULL
                        ORDER BY created_at DESC LIMIT 1""", (formulary_id,))
        if not r or not r["p"]:
            r = q1(conn, "SELECT unit_cost p FROM royan_drug_formulary WHERE id=%s", (formulary_id,))
    if (not r or not r.get("p")) and drug_name:
        r = q1(conn, """SELECT base_price p FROM royan_service_catalog WHERE category='pharmacy' AND upper(name)=upper(%s)
                        AND base_price > 0 LIMIT 1""", (drug_name,))
    return float((r or {}).get("p") or 0)


def unbilled_order_items(conn, encounter_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Everything the doctor ordered on this encounter that is not on a bill yet, priced from the tariff -
    split by company: Royan (lab, drugs) and Scancare (scans)."""
    billed = {(r["source"], r["source_id"]) for r in q(conn, """SELECT source, source_id FROM royan_bill_items
                     WHERE encounter_id=%s AND source IS NOT NULL""", (encounter_id,))}
    royan: List[Dict[str, Any]] = []
    scancare: List[Dict[str, Any]] = []
    for o in q(conn, """SELECT o.id, o.test_name, o.test_code, o.catalog_id, c.base_price, c.name AS cat_name
                        FROM royan_lab_orders o
                        LEFT JOIN LATERAL (SELECT base_price, name FROM royan_lab_catalog lc
                                           WHERE lc.is_active AND (lc.id=o.catalog_id OR lc.code=o.test_code
                                                 OR upper(lc.name)=upper(o.test_name) OR upper(lc.abbreviation)=upper(o.test_name))
                                           ORDER BY (lc.id=o.catalog_id) DESC LIMIT 1) c ON TRUE
                        WHERE o.encounter_id=%s AND o.external_source IS NULL AND COALESCE(o.status,'') NOT IN ('cancelled','rejected')""",
                     (encounter_id,)):
        if ("lab_order", str(o["id"])) in billed:
            continue
        royan.append({"description": o["test_name"] or o["cat_name"] or "Lab test", "category": "lab", "quantity": 1,
                      "unit_price": float(o["base_price"] or 0), "source": "lab_order", "source_id": str(o["id"]),
                      "priced": o["base_price"] is not None})
    for o in q(conn, """SELECT o.id, o.test_name, o.modality, c.base_price
                        FROM royan_radiology_orders o
                        LEFT JOIN LATERAL (SELECT base_price FROM royan_radiology_catalog rc
                                           WHERE rc.id::text=o.radiology_catalog_id::text OR upper(rc.name)=upper(o.test_name)
                                           ORDER BY (rc.id::text=o.radiology_catalog_id::text) DESC LIMIT 1) c ON TRUE
                        WHERE o.encounter_id=%s AND o.external_source IS NULL AND COALESCE(o.status,'') NOT IN ('cancelled')""",
                     (encounter_id,)):
        if ("radiology_order", str(o["id"])) in billed:
            continue
        scancare.append({"description": o["test_name"] or o["modality"] or "Imaging", "category": "imaging", "quantity": 1,
                         "unit_price": float(o["base_price"] or 0), "source": "radiology_order", "source_id": str(o["id"]),
                         "priced": o["base_price"] is not None})
    for p in q(conn, """SELECT id, drug_name, formulary_id, quantity FROM royan_prescriptions
                        WHERE encounter_id=%s AND external_source IS NULL AND COALESCE(status,'') NOT IN ('cancelled','returned')""",
               (encounter_id,)):
        if ("prescription", str(p["id"])) in billed:
            continue
        price = _drug_price(conn, p["formulary_id"], p["drug_name"])
        royan.append({"description": p["drug_name"] or "Medication", "category": "pharmacy", "quantity": float(p["quantity"] or 1),
                      "unit_price": price, "source": "prescription", "source_id": str(p["id"]), "priced": price > 0})
    return {"ROYAN": royan, "SCANCARE": scancare}


def bill_front_desk(encounter_id: int, user: Dict[str, Any], *, specialty: Optional[str] = None, kind: Optional[str] = None,
                    include_registration: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """The front desk bill: registration (new patients) + consultation. Nothing to bill -> None."""
    from src.routers.billing_hospital import create_coverage_bill
    with tx() as conn:
        enc = q1(conn, "SELECT * FROM royan_encounters WHERE id=%s", (encounter_id,))
        if not enc:
            return None
        items = front_desk_items(conn, enc, specialty, kind, include_registration)
    if not items:
        return None
    return create_coverage_bill(encounter_id, int(enc["patient_id"]), items, user, stage="registration",
                                notes="Front desk: registration and consultation")


def bill_orders(encounter_id: int, user: Dict[str, Any]) -> Dict[str, Any]:
    """The doctor sends the patient to the cashier: one bill for what Royan provides, one for Scancare's scans."""
    from src.routers.billing_hospital import create_coverage_bill
    with tx() as conn:
        enc = q1(conn, "SELECT * FROM royan_encounters WHERE id=%s", (encounter_id,))
        if not enc:
            return {"bills": []}
        groups = unbilled_order_items(conn, encounter_id)
    out = []
    for entity, items in groups.items():
        if not items:
            continue
        out.append(create_coverage_bill(encounter_id, int(enc["patient_id"]), [{k: v for k, v in i.items() if k != "priced"} for i in items],
                                        user, entity=entity, stage="services",
                                        notes="Scancare imaging ordered at consultation" if entity == "SCANCARE" else "Ordered at consultation"))
    return {"bills": out, "unpriced": [i["description"] for g in groups.values() for i in g if not i["priced"]]}


def clearance(source: str, source_id: Any) -> Dict[str, Any]:
    """May this order be served yet? ok=True, or ok=False with why and what is owed."""
    with tx() as conn:
        mode = _setting(conn, "pay_first") or "off"
        if mode == "off":
            return {"ok": True, "reason": "pay first is off"}
        rel = q1(conn, "SELECT reason, released_by FROM royan_service_releases WHERE source=%s AND source_id=%s", (source, str(source_id)))
        if rel:
            return {"ok": True, "reason": f"released by {rel['released_by']}: {rel['reason']}"}
        item = q1(conn, """SELECT i.billing_id, b.bill_number, b.status, b.released_at, b.patient_balance, b.encounter_id, b.entity,
                                  e.payer_type, e.encounter_type, e.bed_id, i.payer_type AS line_payer
                           FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                           LEFT JOIN royan_encounters e ON e.id=b.encounter_id
                           WHERE i.source=%s AND i.source_id=%s ORDER BY i.id DESC LIMIT 1""", (source, str(source_id)))
        order_enc = None
        if not item:
            table = {"lab_order": "royan_lab_orders", "radiology_order": "royan_radiology_orders",
                     "prescription": "royan_prescriptions"}.get(source)
            if table:
                when = {"royan_lab_orders": "o.ordered_at", "royan_radiology_orders": "COALESCE(o.ordered_at, o.created_at)",
                        "royan_prescriptions": "o.prescribed_at"}[table]
                since = _setting(conn, "pay_first_since")
                order_enc = q1(conn, f"""SELECT e.payer_type, e.encounter_type, e.bed_id, e.external_source,
                                                ({when} < %s::timestamptz) AS before_pay_first
                                         FROM {table} o LEFT JOIN royan_encounters e ON e.id=o.encounter_id WHERE o.id=%s""",
                               (since or "1900-01-01", source_id))
                # orders placed before pay-first started are not held up (the patient was already mid-visit)
                if order_enc and order_enc.get("before_pay_first"):
                    return {"ok": True, "reason": "ordered before pay-first started"}
        ctx = item or order_enc or {}
        if ctx.get("external_source"):
            return {"ok": True, "reason": "migrated history"}
        if (ctx.get("payer_type") or "") in ("hmo", "staff") or (ctx.get("line_payer") or "") in ("hmo", "staff"):
            return {"ok": True, "reason": "HMO / staff scheme - claimed, not paid at the till"}
        if (ctx.get("encounter_type") or "outpatient") != "outpatient" or ctx.get("bed_id"):
            return {"ok": True, "reason": "admitted - on the running bill"}
        if not item:
            return {"ok": False, "reason": "Not billed yet - send the patient to the cashier (the doctor's 'Send to cashier')."}
        if item["status"] in ("paid", "waived"):
            return {"ok": True, "reason": f"bill {item['bill_number']} {item['status']}"}
        if item["status"] == "partial" and item["released_at"]:
            return {"ok": True, "reason": f"bill {item['bill_number']} part-paid, released by the cashier"}
        return {"ok": False, "bill_id": item["billing_id"], "bill_number": item["bill_number"],
                "reason": f"Bill {item['bill_number']} is {item['status']} - the patient pays at the cashier first."}


def visit_clearance(encounter_id: Any) -> Dict[str, Any]:
    """May the patient go on to the next step of the visit (vitals, the doctor, the results review)? Royan's rule
    (finance meeting): after every stop the patient pays at the cashier before the next service. Private outpatients
    only; HMO / staff schemes are claimed, admitted patients run a bill, and an emergency is never held at the till.
    A part-paid bill the cashier released counts as cleared."""
    with tx() as conn:
        mode = _setting(conn, "pay_first") or "off"
        if mode == "off":
            return {"ok": True, "reason": "pay first is off"}
        enc = q1(conn, """SELECT payer_type, encounter_type, bed_id, arrival_priority, triage_level, external_source
                          FROM royan_encounters WHERE id=%s""", (encounter_id,))
        if not enc or enc.get("external_source"):
            return {"ok": True, "reason": "not a live visit"}
        if (enc.get("payer_type") or "") in ("hmo", "staff"):
            return {"ok": True, "reason": "HMO / staff scheme - claimed, not paid at the till"}
        if (enc.get("encounter_type") or "outpatient") != "outpatient" or enc.get("bed_id"):
            return {"ok": True, "reason": "admitted - on the running bill"}
        if enc.get("arrival_priority") == "emergency" or enc.get("triage_level") == "immediate":
            return {"ok": True, "reason": "emergency - care first, payment after"}
        unpaid = q(conn, """SELECT b.bill_number, b.patient_balance - COALESCE(p.paid, 0) AS owed
                            FROM royan_billing b
                            LEFT JOIN LATERAL (SELECT SUM(amount) AS paid FROM royan_payments
                                               WHERE billing_id=b.id AND COALESCE(status,'posted') <> 'void') p ON true
                            WHERE b.encounter_id=%s AND b.status IN ('pending','partial','disputed') AND b.released_at IS NULL
                              AND b.patient_balance - COALESCE(p.paid, 0) > 0.009 ORDER BY b.id""", (encounter_id,))
    if not unpaid:
        return {"ok": True, "reason": "nothing owed"}
    owed = sum(float(r["owed"]) for r in unpaid)
    bills = ", ".join(r["bill_number"] for r in unpaid)
    return {"ok": False, "owed": round(owed, 2), "bills": [r["bill_number"] for r in unpaid],
            "reason": f"₦{owed:,.2f} to pay first ({bills}) - the patient pays at the cashier before the next service."}


def require_visit_clearance(encounter_id: Any) -> None:
    from fastapi import HTTPException
    c = visit_clearance(encounter_id)
    if not c["ok"]:
        raise HTTPException(status_code=402, detail=c["reason"] + " The cashier can release a part-paid bill if needed.")


def require_clearance(source: str, source_id: Any) -> None:
    """Raise 402 with a clear message when an order may not be served yet."""
    from fastapi import HTTPException
    c = clearance(source, source_id)
    if not c["ok"]:
        raise HTTPException(status_code=402, detail=c["reason"] + " A supervisor can release it if needed.")
