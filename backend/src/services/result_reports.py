"""Lab and Scancare results as the printed report the patient and doctor receive (the Scancare template:
docs/scan care template and logo). The lab and Scancare enter findings; this turns them into the report - patient
block, the department heading ("BIOCHEMISTRY REPORT"), one line per investigation (observed value, units, normal
range) or, for a scan, the radiologist's report - and the staff who resulted and verified it.

  lab_report([order_ids])   one or more lab orders of the same patient, grouped by department
  scan_report(order_id)     one Scancare (radiology) order

Every result shape in the database reads the same way: template / parameter rows (result_data.analytes), a single
value (result_data.value), and Hope's history (one result row per parameter: {"parameter", "result"} or {"text"}).
"""
from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any, Dict, Iterable, List, Optional

from src.fin.db import q, q1, tx

LAGOS = dt.timezone(dt.timedelta(hours=1))
NOTE = "Assay result should be interpreted only in the context of other laboratory finding and the total clinical status of the patient."


def _age(born: Optional[dt.date]) -> Optional[int]:
    if not born:
        return None
    t = dt.date.today()
    return t.year - born.year - ((t.month, t.day) < (born.month, born.day))


def _when(v: Any) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v.astimezone(LAGOS).strftime("%d/%m/%Y %H:%M:%S") if v.tzinfo else v.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def _people(conn, ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """Login ids / staff ids -> name and title, for the signature lines."""
    want = sorted({str(x) for x in ids if x})
    if not want:
        return {}
    rows = q(conn, """SELECT s.id::text AS staff_id, s.user_id::text AS user_id, s.full_name, s.designation, s.role, u.email
                      FROM royan_staff s LEFT JOIN royan_users u ON u.id = s.user_id
                      WHERE s.id::text = ANY(%s) OR s.user_id::text = ANY(%s) OR lower(s.email) = ANY(%s)""",
             (want, want, [w.lower() for w in want]))
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        title = (r.get("designation") or "").strip() or {"lab": "Medical Laboratory Scientist", "radiology": "Radiologist",
                                                         "doctor": "Doctor"}.get((r.get("role") or "").lower(), "")
        p = {"name": (r.get("full_name") or "").upper(), "title": title.upper()}
        for k in (r.get("staff_id"), r.get("user_id"), (r.get("email") or "").lower()):
            if k:
                out[k] = p
    for w in want:          # an id with no staff record still prints something readable
        if w not in out and w.lower() not in out and "@" in w:
            out[w] = {"name": w.split("@")[0].replace(".", " ").upper(), "title": ""}
    return {k: v for k, v in out.items() if k in want or k in {w.lower() for w in want}}


def _patient_block(conn, patient_id: int, encounter_id: Optional[int], ref_by: Optional[str]) -> Dict[str, Any]:
    p = q1(conn, "SELECT * FROM royan_patients WHERE id=%s", (patient_id,)) or {}
    enc = q1(conn, "SELECT * FROM royan_encounters WHERE id=%s", (encounter_id,)) if encounter_id else None
    diagnosis = None
    if enc:
        try:
            from src.routers.billing_hospital import visit_diagnoses
            dx = visit_diagnoses(conn, enc["id"])
            diagnosis = ", ".join(d.get("description") or d.get("icd_code") or "" for d in dx[:2]) or None
        except Exception:
            diagnosis = None
        if not enc.get("external_source") and not (enc.get("diagnosis_notes") or "").startswith("Consolidated"):
            diagnosis = diagnosis or enc.get("diagnosis_notes")
    gender = (p.get("gender") or "").strip().title()
    age = _age(p.get("date_of_birth"))
    return {
        "patient_name": " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x).upper() or "-",
        "patient_id": p.get("mrn"),
        "age_gender": "/".join(x for x in ((f"{age} Years" if age is not None else None), gender or None) if x) or "-",
        "mobile": p.get("phone"),
        "ref_by": (ref_by or _ref_name((enc or {}).get("consulting_doctor")) or "SELF REFERRED").upper(),
        "consultant": (_ref_name((enc or {}).get("consulting_doctor")) or "").upper() or None,
        "provisional_diagnosis": diagnosis,
        "printed_at": _when(dt.datetime.now(dt.timezone.utc)),
    }


# The department heading for a test the catalog does not place (most Hope tests), as Scancare's reports head them.
_DEPARTMENTS = [
    ("CHEMISTRY", ("URINALYSIS", "URINE")),
    ("SEROLOGY", ("HIV", "HBSAG", "HEPATITIS", "HCV", "VDRL", "WIDAL", "H. PYLORI", "H.PYLORI", "PYLORI", "RHEUMATOID",
                  "ASO", "CRP", "RETRO", "SYPHILIS")),
    ("ENDOCRINOLOGY", ("THYROID", "TSH", "T3", "T4", "HORMON", "PROLACTIN", "FSH", "LH", "PROGESTERONE", "OESTROGEN",
                       "ESTRADIOL", "TESTOSTERONE", "PSA", "BETA HCG", "B-HCG", "INSULIN", "CORTISOL")),
    ("PARASITOLOGY", ("MALARIA", "MP ", "STOOL", "OVA", "PARASITE", "SKIN SNIP")),
    ("MICROBIOLOGY", ("CULTURE", "M/C/S", "MCS", "SWAB", "GRAM", "AFB", "SENSITIVITY")),
    ("BIOCHEMISTRY", ("ELECTROLYTE", "UREA", "CREATININE", "E/U/CR", "EUCR", "LIVER FUNCTION", "LFT", "LIPID", "CHOLESTEROL",
                      "GLUCOSE", "SUGAR", "FBS", "RBS", "HBA1C", "URIC", "CALCIUM", "BILIRUBIN", "PROTEIN", "ALBUMIN",
                      "AMYLASE", "PHOSPHATE", "MAGNESIUM", "KIDNEY", "RENAL", "OGTT", "TRIGLYCERIDE", "ALKALINE")),
    ("HAEMATOLOGY", ("FBC", "BLOOD COUNT", "PCV", "HB ", "HAEMOGLOBIN", "HEMOGLOBIN", "ESR", "GENOTYPE", "BLOOD GROUP",
                     "PLATELET", "WBC", "CLOTTING", "BLEEDING", "PT/INR", "INR", "SICKLING", "RETICULOCYTE", "CROSS MATCH")),
    ("IMMUNOLOGY", ("PREGNANCY", "HCG")),
]


def department(test_name: Optional[str], category: Optional[str]) -> str:
    name = f" {(test_name or '').upper()} "
    for dept, keys in _DEPARTMENTS:
        if any(k in name for k in keys):
            return dept
    return (category or "").strip().upper() or "LABORATORY"


def _ref_name(v: Any) -> Optional[str]:
    """A free-text ordering doctor worth printing (not an id, an email or a system marker)."""
    t = str(v or "").strip()
    if not t or "@" in t or len(t) > 40 or not re.search(r"[A-Za-z]{3}", t) or "_" in t or re.fullmatch(r"[0-9a-f-]{32,36}", t):
        return None
    return t


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _range(a: Dict[str, Any]) -> Optional[str]:
    if a.get("reference_range"):
        return str(a["reference_range"])
    lo, hi = a.get("normal_low"), a.get("normal_high")
    if lo is not None and hi is not None:
        return f"{lo:g} - {hi:g}" if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else f"{lo} - {hi}"
    if lo is not None:
        return f">= {lo}"
    if hi is not None:
        return f"<= {hi}"
    return None


def _flag(value: Any, rng: Optional[str], given: Optional[bool]) -> Optional[str]:
    """H / L against the printed range when the value and range are numbers; the entered flag otherwise."""
    v = _num(value)
    m = re.match(r"^\s*([\d.]+)\s*[-–]\s*([\d.]+)", rng or "")
    if v is not None and m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if v < lo:
            return "L"
        if v > hi:
            return "H"
        return None
    return "*" if given else None


def _rows(results: List[Dict[str, Any]], test_name: str) -> tuple:
    """(rows, notes) for one order from its result rows."""
    rows: List[Dict[str, Any]] = []
    notes: List[str] = []
    for r in results:
        data = r.get("result_data") or {}
        if isinstance(data, dict) and data.get("analytes"):
            for a in data["analytes"]:
                rng = _range(a)
                val = a.get("observed_value", a.get("value"))
                rows.append({"name": a.get("name"), "value": val, "unit": a.get("unit"), "range": rng,
                             "flag": "C" if a.get("is_critical") else _flag(val, rng, a.get("is_abnormal")),
                             "comment": a.get("comment")})
        elif isinstance(data, dict) and data.get("parameter"):
            rng = data.get("range") or r.get("reference_range")          # Hope: {"parameter","result","uom","range"}
            rows.append({"name": data["parameter"], "value": data.get("result"), "unit": data.get("uom") or data.get("unit"),
                         "range": rng, "flag": _flag(data.get("result"), rng, None)})
        elif isinstance(data, dict) and data.get("value") is not None:
            rows.append({"name": test_name, "value": data.get("value"), "unit": data.get("unit"), "range": r.get("reference_range"),
                         "flag": _flag(data.get("value"), r.get("reference_range"), r.get("interpretation") in ("abnormal", "critical"))})
        elif isinstance(data, dict) and data.get("text"):
            notes.append(html.unescape(str(data["text"])).replace("\r\n", "\n").strip())
        elif r.get("result_summary"):
            rows.append({"name": test_name, "value": r["result_summary"], "unit": None, "range": r.get("reference_range"), "flag": None})
        if r.get("notes") and not r.get("external_source"):
            notes.append(str(r["notes"]).strip())
    return rows, notes


def lab_report(order_ids: List[int]) -> Dict[str, Any]:
    if not order_ids:
        raise LookupError("No lab order given")
    with tx() as conn:
        orders = q(conn, """SELECT o.*, c.category, c.unit AS cat_unit, c.reference_range AS cat_range
                            FROM royan_lab_orders o
                            LEFT JOIN LATERAL (SELECT category, unit, reference_range FROM royan_lab_catalog lc
                                               WHERE lc.id = o.catalog_id OR upper(lc.name) = upper(o.test_name)
                                               ORDER BY (lc.id = o.catalog_id) DESC LIMIT 1) c ON true
                            WHERE o.id = ANY(%s) ORDER BY o.id""", (order_ids,))
        if not orders:
            raise LookupError("Lab order not found")
        if len({o["patient_id"] for o in orders}) > 1:
            raise ValueError("A report covers one patient's tests")
        results = q(conn, """SELECT * FROM royan_lab_results WHERE lab_order_id = ANY(%s) ORDER BY lab_order_id, id""",
                    ([o["id"] for o in orders],))
        specimens = {r["lab_order_id"]: r for r in q(conn, """SELECT DISTINCT ON (lab_order_id) lab_order_id, collected_at, received_at
                                                               FROM royan_lab_specimens WHERE lab_order_id = ANY(%s)
                                                               ORDER BY lab_order_id, id DESC""", ([o["id"] for o in orders],))}
        first = orders[0]
        doctor = None
        if first.get("ordered_by_id"):
            d = _people(conn, [first["ordered_by_id"]]).get(str(first["ordered_by_id"]))
            doctor = d["name"] if d else None
        head = _patient_block(conn, first["patient_id"], first.get("encounter_id"), doctor or _ref_name(first.get("ordered_by")))

        by_order: Dict[int, List[Dict[str, Any]]] = {}
        for r in results:
            by_order.setdefault(r["lab_order_id"], []).append(r)
        sections: Dict[str, Dict[str, Any]] = {}
        signer_ids: List[Any] = []
        received: List[Any] = []
        for o in orders:
            rs = by_order.get(o["id"], [])
            native = [r for r in rs if not r.get("external_source")]
            use = [native[-1]] if native else rs            # a native order: the latest version (amendments supersede)
            rows, notes = _rows(use, o["test_name"])
            if rows and len(rows) == 1 and not rows[0].get("unit") and o.get("cat_unit"):
                rows[0]["unit"] = o["cat_unit"]
            if rows and len(rows) == 1 and not rows[0].get("range") and o.get("cat_range"):
                rows[0]["range"] = o["cat_range"]
            # the test's name decides (the catalog files most tests under haematology); the catalog only as a fallback
            dept = department(o.get("test_name"), o.get("category"))
            sec = sections.setdefault(dept, {"heading": f"{dept} REPORT", "tests": []})
            sec["tests"].append({"order_id": o["id"], "test_name": (o["test_name"] or "").upper(), "status": o["status"],
                                 "rows": rows, "notes": notes, "resulted": bool(use),
                                 "verified": any(r.get("verified_at") for r in use),
                                 "amended": any(r.get("amends_result_id") for r in use)})
            for r in use:
                signer_ids += [r.get("resulted_by"), r.get("verified_by")]
            sp = specimens.get(o["id"]) or {}
            received.append(sp.get("received_at") or sp.get("collected_at") or o.get("sample_collected_at"))
        people = _people(conn, signer_ids)
    signatories, seen = [], set()
    for sid in signer_ids:
        p = people.get(str(sid)) if sid else None
        if p and p["name"] not in seen:
            seen.add(p["name"])
            signatories.append(p)
    got = [x for x in received if x]
    return {
        "kind": "lab", "company": "SCANCARE",
        **head,
        "sample_received": _when(min(got)) if got else None,
        "request_no": ", ".join(str(o["id"]) for o in orders),
        "sections": list(sections.values()),
        "note": NOTE,
        "signatories": signatories[:3],
        "complete": all(t["resulted"] for s in sections.values() for t in s["tests"]),
    }


def scan_report(order_id: int) -> Dict[str, Any]:
    with tx() as conn:
        o = q1(conn, "SELECT * FROM royan_radiology_orders WHERE id=%s", (order_id,))
        if not o:
            raise LookupError("Scan order not found")
        doctor = None
        if o.get("ordered_by"):
            d = _people(conn, [o["ordered_by"]]).get(str(o["ordered_by"]))
            doctor = d["name"] if d else None
        head = _patient_block(conn, o["patient_id"], o.get("encounter_id"),
                              doctor or _ref_name(o.get("ordering_doctor")))
        people = _people(conn, [o.get("radiologist_id"), o.get("verified_by")])
    signatories, seen = [], set()
    for sid in (o.get("radiologist_id"), o.get("verified_by")):
        p = people.get(str(sid)) if sid else None
        if p and p["name"] not in seen:
            seen.add(p["name"])
            signatories.append(p)
    modality = (o.get("modality") or "").upper()
    name = (o.get("test_name") or "").upper()
    heading = "ULTRASOUND REPORT" if "ULTRASOUND" in name or modality in ("US", "ULTRASOUND") else \
        "X-RAY REPORT" if "X-RAY" in name or "XRAY" in name or modality in ("XR", "CR", "DX", "X-RAY") else \
        "CT SCAN REPORT" if "CT" in name.split() or modality == "CT" else \
        "MRI REPORT" if "MRI" in name or modality == "MR" else "RADIOLOGY REPORT"
    return {
        "kind": "scan", "company": "SCANCARE",
        **head,
        "sample_received": _when(o.get("started_at") or o.get("scheduled_at") or o.get("ordered_at") or o.get("order_date")),
        "request_no": str(o["id"]),
        "heading": heading,
        "test_name": name,
        "clinical_indication": o.get("clinical_indication"),
        "report": html.unescape(o.get("report") or "").replace("\r\n", "\n").strip() or None,
        "findings": html.unescape(o.get("findings") or "").replace("\r\n", "\n").strip() or None,
        "impression": html.unescape(o.get("impression") or "").replace("\r\n", "\n").strip() or None,
        "reported_at": _when(o.get("reported_at")),
        "verified": bool(o.get("verified_at")),
        "status": o.get("status"),
        "signatories": signatories,
        "complete": bool(o.get("report") or o.get("findings") or o.get("impression")),
    }
