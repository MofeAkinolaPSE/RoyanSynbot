"""Load every Hope charge line, with its payer, into Roy Books.

    python -m src.fin.hope_charges --staging ../data-assimilation/staging/hope_staging.db [--dry-run]

Hope priced every line against the patient's payer (its "tariff standard":
Private, an HMO, a staff scheme, a retainership ...). Sage only ever saw
totals: HMO invoices in the sales journal and the day's private takings as
general journals. These lines are what lets Roy Books split revenue between
HMOs and private patients at line level and reconcile Hope against Sage.

  fin_hope_payers   <- raw_hope_tariff_standards (one per payer), typed by name
                       (PRIVATE / HMO / STAFF / CORPORATE / INTERNAL), linked to the hospital's
                       HMO (royan_hmos.external_id = tariff id) and its Roy Books
                       debtor. Re-typing done by Finance is never overwritten.
  fin_hope_charges  <- raw_billing (services), raw_hope_pharmacy_sales_bills,
                       raw_lab, raw_hope_radiology_test_orders,
                       raw_hope_ward_patient_services. Deleted lines are skipped.
                       Lines without their own payer take the visit's.

Display and reconciliation only - nothing posts. Upserts on (source, Hope id), so
re-running refreshes. Like hope_history, the staging database lives on the
development machine; the rows reach the hospital's server with the database dump.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Dict, Iterator, Optional, Tuple

from psycopg2.extras import execute_values

from src.fin.context import resolve_entity
from src.fin.db import ex, q, tx
from src.fin.hope_history import _clean, _date, _dec

ZERO = Decimal("0")
MIS_KEYED = Decimal("1000000000")   # a single Hope line of N1bn+ is a keying error (amount typed into a quantity field)
CORPORATE_WORDS = ("RETAINERSHIP", "MONTHLY BILLING", "FAMILY", "CHURCH", "SCHOOL", "SCANCARE", "ANAESTHETIST",
                   "LAP WITH", "BABYBLISS", "NIMASA", "NIGERBEV", "NNPC")


def payer_type(tariff_id: str, name: str) -> str:
    n = (name or "").upper()
    if tariff_id == "7" or n.strip() in ("PRIVATE", "GENERAL", "CASH"):
        return "PRIVATE"
    if n.startswith("FOR SCANCARE ONLY"):     # Scancare work Royan pays for on its patients' behalf - not a receivable
        return "INTERNAL"
    if "STAFF" in n:
        return "STAFF"
    if n.startswith("SCANCARE RADIOLOGY"):   # Scancare's own walk-in lab/imaging customers pay at the till
        return "PRIVATE"
    if "HMO" not in n and any(w in n for w in CORPORATE_WORDS):
        return "CORPORATE"
    return "HMO"


def _rows(c: sqlite3.Connection, table: str) -> Iterator[Dict[str, Any]]:
    for (data,) in c.execute(f"SELECT data FROM {table}"):
        yield json.loads(data)


def _names(c: sqlite3.Connection, table: str) -> Dict[str, str]:
    return {str(r["id"]): (r.get("name") or "").strip() for r in _rows(c, table)}


def load_payers(conn, c: sqlite3.Connection) -> Dict[str, Any]:
    hmo = {r["external_id"]: r["id"] for r in q(conn, "SELECT id, external_id FROM royan_hmos WHERE external_source='hope'")}
    cust = {r["hmo_id"]: r["id"] for r in q(conn, "SELECT id, hmo_id FROM fin_customers WHERE hmo_id IS NOT NULL")}
    n = defaultdict(int)
    for t in _rows(c, "raw_hope_tariff_standards"):
        tid, name = str(t["id"]), (t.get("name") or "").strip() or f"Payer {t['id']}"
        kind = payer_type(tid, name)
        h = hmo.get(tid)
        cid = cust.get(h) if h else None
        ex(conn, """INSERT INTO fin_hope_payers (tariff_id, name, payer_type, hmo_id, customer_id)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (tariff_id) DO UPDATE SET name=EXCLUDED.name, hmo_id=EXCLUDED.hmo_id,
                        payer_type=CASE WHEN fin_hope_payers.typed_by='rule' THEN EXCLUDED.payer_type ELSE fin_hope_payers.payer_type END,
                        updated_at=now()""",
           (int(tid), name, kind, h, cid))
        n[kind] += 1
    return dict(n)


NOISE = {"nhis", "for", "only", "paid", "by", "royan", "scancare", "patients", "patient", "hmos", "partners_"}


def _words(name: str) -> list:
    from src.fin.sage_import import GENERIC
    return [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in GENERIC and w not in NOISE]


def link_accounts(conn) -> Dict[str, Any]:
    """Each Sage HMO / corporate account -> the Hope payer it is (several accounts can be one payer: Mansard was billed
    as an HMO and under NHIS). Same HMO record, same name, or the same distinctive words allowing Sage's typos
    ("Achor", "Multisheild"). Links someone made by hand are kept."""
    payers = q(conn, """SELECT tariff_id, name, hmo_id, payer_type FROM fin_hope_payers
                        WHERE payer_type IN ('HMO','CORPORATE') AND name NOT ILIKE '%%scancare%%'""")
    custs = q(conn, """SELECT c.id, c.name, c.hmo_id FROM fin_customers c
                       WHERE c.party_type IN ('HMO','CORPORATE') AND EXISTS (SELECT 1 FROM fin_sage_customers s WHERE s.customer_id=c.id)""")
    manual = {r["customer_id"] for r in q(conn, "SELECT customer_id FROM fin_hope_payer_accounts WHERE linked_by <> 'rule'")}
    ex(conn, "DELETE FROM fin_hope_payer_accounts WHERE linked_by='rule'")
    by_hmo = {p["hmo_id"]: p for p in payers if p["hmo_id"]}
    stats = defaultdict(int)
    for c in custs:
        if c["id"] in manual:
            continue
        best, method = None, None
        if c["hmo_id"] and c["hmo_id"] in by_hmo:
            best, method = by_hmo[c["hmo_id"]], "same HMO record"
        else:
            cn, cw = re.sub(r"[^a-z0-9]", "", c["name"].lower()), _words(c["name"])
            scored = []
            for p in payers:
                pw = _words(p["name"])
                if re.sub(r"[^a-z0-9]", "", p["name"].lower()) == cn:
                    scored.append((2.0, p))
                    continue
                if not pw or not cw:
                    continue
                r0 = SequenceMatcher(None, pw[0], cw[0]).ratio()
                if r0 < 0.85 or min(len(pw[0]), len(cw[0])) < 4:
                    continue
                if len(pw) > 1 and len(cw) > 1:
                    r1 = SequenceMatcher(None, pw[1], cw[1]).ratio()
                    if r1 < 0.85:
                        continue
                    r0 = (r0 + r1) / 2
                scored.append((r0 - 0.01 * abs(len(pw) - len(cw)), p))   # "Achor" is Anchor before Anchor TPA
            scored.sort(key=lambda x: -x[0])
            if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                best, method = scored[0][1], "same name" if scored[0][0] == 2.0 else f"similar name ({scored[0][0]:.2f})"
        if best:
            ex(conn, """INSERT INTO fin_hope_payer_accounts (customer_id, tariff_id, match_method) VALUES (%s,%s,%s)
                        ON CONFLICT (customer_id) DO NOTHING""", (c["id"], best["tariff_id"], method))
            stats["linked"] += 1
        else:
            stats["no_payer"] += 1
    # The payer's own account: its HMO record's debtor, else its largest linked Sage account.
    ex(conn, """UPDATE fin_hope_payers p SET customer_id = COALESCE(
                    (SELECT c.id FROM fin_customers c WHERE c.hmo_id=p.hmo_id AND p.hmo_id IS NOT NULL LIMIT 1),
                    (SELECT a.customer_id FROM fin_hope_payer_accounts a LEFT JOIN fin_sage_invoices i ON i.customer_id=a.customer_id
                     WHERE a.tariff_id=p.tariff_id GROUP BY a.customer_id ORDER BY SUM(i.amount) DESC NULLS LAST LIMIT 1)),
                    sage_code = (SELECT string_agg(s.sage_code, ', ' ORDER BY s.sage_code) FROM fin_hope_payer_accounts a
                                 JOIN fin_sage_customers s ON s.customer_id=a.customer_id WHERE a.tariff_id=p.tariff_id)""")
    stats["payers_with_sage_account"] = q(conn, "SELECT COUNT(DISTINCT tariff_id) n FROM fin_hope_payer_accounts")[0]["n"]
    return dict(stats)


def _num(v: Any) -> Decimal:
    return _dec(v) or ZERO


def _line(source: str, r: Dict[str, Any], visits: Dict[str, Tuple[str, Optional[str]]], when: Any, service: Optional[str],
          category: Optional[str], qty: Decimal, unit: Decimal, gross: Optional[Decimal], ref: Optional[str]) -> Optional[tuple]:
    if str(r.get("is_deleted") or "0") == "1":
        return None
    d = _date(when) or _date(r.get("create_time"))
    if not d:
        return None
    vid = str(r.get("patient_id") or "")
    mrn, vt = visits.get(vid, (None, None))
    tariff = str(r.get("tariff_standard_id") or "") or vt
    g = gross if gross is not None else unit * qty
    cash, card = _num(r.get("paid_by_cash")), _num(r.get("paid_by_card"))
    paid = _num(r.get("paid_amount") if "paid_amount" in r else r.get("paid_amnt")) or (cash + card)
    if g <= 0 and paid <= 0:
        return None
    if max(g, paid, cash + card, unit) >= MIS_KEYED:
        return ("MIS_KEYED", source, int(r["id"]), g)
    sb = r.get("corporate_super_bill_id")
    return (source, int(r["id"]), int(vid) if vid.isdigit() else None, mrn, d, service, category,
            int(tariff) if tariff and tariff.isdigit() else None, qty, g, _num(r.get("discount")), cash, card, paid,
            ref, int(sb) if str(sb or "").isdigit() and str(sb) != "0" else None)


def load_charges(conn, c: sqlite3.Connection) -> Dict[str, Any]:
    visits: Dict[str, Tuple[str, Optional[str]]] = {}
    for v in _rows(c, "raw_patients"):
        visits[str(v["id"])] = (_clean(v.get("patient_id")), _clean(v.get("tariff_standard_id")))
    tariff_list, categories = _names(c, "raw_hope_tariff_lists"), _names(c, "raw_hope_service_categories")
    labs, rads = _names(c, "raw_hope_laboratories"), _names(c, "raw_hope_radiologies")
    one = Decimal("1")

    def sources():
        for r in _rows(c, "raw_billing"):
            yield _line("SERVICE", r, visits, r.get("date"), tariff_list.get(str(r.get("tariff_list_id"))),
                        categories.get(str(r.get("service_id"))), _num(r.get("no_of_times")) or one, _num(r.get("amount")), None, None)
        for r in _rows(c, "raw_hope_pharmacy_sales_bills"):
            yield _line("PHARMACY", r, visits, r.get("create_time"), "Pharmacy sale", "PHARMACY", one, ZERO,
                        _num(r.get("total")), _clean(r.get("bill_code")))
        for r in _rows(c, "raw_lab"):
            yield _line("LAB", r, visits, r.get("start_date"), labs.get(str(r.get("laboratory_id"))), "LABORATORY", one,
                        _num(r.get("amount")), None, _clean(r.get("order_id")))
        for r in _rows(c, "raw_hope_radiology_test_orders"):
            yield _line("RADIOLOGY", r, visits, r.get("radiology_order_date"),
                        _clean(r.get("testname")) or rads.get(str(r.get("radiology_id"))), "RADIOLOGY", one,
                        _num(r.get("amount")), None, _clean(r.get("order_id")))
        for r in _rows(c, "raw_hope_ward_patient_services"):
            yield _line("WARD", r, visits, r.get("date"), tariff_list.get(str(r.get("tariff_list_id"))),
                        categories.get(str(r.get("service_id"))) or "WARD", _num(r.get("unit")) or one, _num(r.get("amount")),
                        None, None)

    stats: Dict[str, Any] = defaultdict(lambda: {"lines": 0, "gross": ZERO})
    batch = []

    def flush():
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO fin_hope_charges (source, hope_id, visit_id, mrn, charge_date, service, category, payer_tariff_id,
                    quantity, gross, discount, paid_cash, paid_card, paid, reference, super_bill_id) VALUES %s
                ON CONFLICT (source, hope_id) DO UPDATE SET visit_id=EXCLUDED.visit_id, mrn=EXCLUDED.mrn,
                    charge_date=EXCLUDED.charge_date, service=EXCLUDED.service, category=EXCLUDED.category,
                    payer_tariff_id=EXCLUDED.payer_tariff_id, quantity=EXCLUDED.quantity, gross=EXCLUDED.gross,
                    discount=EXCLUDED.discount, paid_cash=EXCLUDED.paid_cash, paid_card=EXCLUDED.paid_card, paid=EXCLUDED.paid,
                    reference=EXCLUDED.reference, super_bill_id=EXCLUDED.super_bill_id""", batch, page_size=5000)
        batch.clear()

    mis_keyed = []
    for line in sources():
        if not line:
            continue
        if line[0] == "MIS_KEYED":
            mis_keyed.append({"source": line[1], "hope_id": line[2], "gross": str(line[3])})
            continue
        batch.append(line)
        s = stats[line[0]]
        s["lines"] += 1
        s["gross"] += line[9]
        if len(batch) >= 20000:
            flush()
    if batch:
        flush()
    ex(conn, """UPDATE fin_hope_charges h SET patient_id=p.id FROM royan_patients p
                WHERE p.mrn=h.mrn AND h.patient_id IS DISTINCT FROM p.id""")
    out = {k: {"lines": v["lines"], "gross": str(v["gross"])} for k, v in stats.items()}
    out["mis_keyed_skipped"] = {"lines": len(mis_keyed), "examples": mis_keyed[:10]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staging", required=True, help="path to hope_staging.db")
    ap.add_argument("--dry-run", action="store_true", help="load inside a transaction and roll it back")
    ap.add_argument("--payers-only", action="store_true", help="refresh payers and their Sage accounts, not the lines")
    args = ap.parse_args()
    c = sqlite3.connect(args.staging)
    with tx() as conn:
        entity = resolve_entity(conn, None)
        res = {"payers": load_payers(conn, c)}
        if not args.payers_only:
            res["charges"] = load_charges(conn, c)
        res["sage_accounts"] = link_accounts(conn)
        res["patients_linked"] = q(conn, "SELECT COUNT(*) n FROM fin_hope_charges WHERE patient_id IS NOT NULL")[0]["n"]
        ex(conn, """INSERT INTO fin_audit_events (legal_entity_id, actor_id, actor_name, action, entity_type, entity_id, metadata)
                    VALUES (%s,'hope-charges','hope-charges','HOPE_CHARGES_LOADED','history',%s,%s)""",
           (entity, entity, json.dumps(res)))
        print(json.dumps(res, indent=2))
        if args.dry_run:
            raise SystemExit("dry run - rolled back")


if __name__ == "__main__":
    main()
