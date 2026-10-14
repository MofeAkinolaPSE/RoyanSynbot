"""Data issues: everything Royan's data leaves unexplained, with its lineage and how to resolve it.

Sage's reports are the acceptance bar and Hope is the record of what was billed. Where the two (or the books and the
pharmacy's shelves) disagree, the difference is not hidden: it becomes an issue in Close & Controls › Data issues.

    kind                       detected from                                         resolutions
    TB_HISTORY                 Sage's trial balance vs the history at its date       correcting journal, accept
    HISTORY_GAP                Sage stops before Hope (and today)                    upload the next Sage set, accept
    INVENTORY_OPENING          shelf stock the ledger and books do not carry          load opening stock at go-live, accept
    STOCK_NO_COST              shelf batches with no unit cost                         enter costs in Pharmacy, accept
    STOCK_EXPIRED              expired batches still on the shelf                      write off / return, accept
    PAYER_NO_SAGE_ACCOUNT      a Hope payer billed ₦1m+ with no Sage account           link its Sage account, retype, accept
    HMO_BILLED_NOT_INVOICED    Hope billed an HMO well beyond what Sage invoiced it    correcting journal, accept
    HOPE_SAGE_PRIVATE_GAP      a year's private billing in Hope vs Sage revenue       accept
    SAGE_INVOICES_UNLINKED     Sage invoices whose receipt named another invoice      accept
    INACTIVE_WITH_BALANCE      an inactive account still carrying a balance           reactivate, correcting journal, accept

refresh() runs the checks (after every Sage load and on "Check again"). An issue the data no longer shows closes itself
("cleared by data"); one that comes back reopens unless it was accepted. A correcting journal (source DATA_CORRECTION,
the General Journal's ADJ lines) is numbered FIX-nnnnnn, dated where the user says (default: the last Sage day), and the
journal and the issue open each other.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from src.fin import audit, posting
from src.fin.db import ZERO, ex, jsonb, money, q, q1
from src.fin.errors import FinError, invalid, not_found
from src.fin.numbering import next_number

PRIVATE_GAP_TOLERANCE = Decimal("0.10")
MIN_PAYER_BILLED = Decimal("1000000")

TITLES = {
    "TB_HISTORY": "Sage trial balance vs history", "HISTORY_GAP": "No Sage books after its last export",
    "INVENTORY_OPENING": "Pharmacy stock not in the books", "STOCK_NO_COST": "Stock without a unit cost",
    "STOCK_EXPIRED": "Expired stock on the shelf", "PAYER_NO_SAGE_ACCOUNT": "Payer with no Sage account",
    "HMO_BILLED_NOT_INVOICED": "HMO billed in Hope but not invoiced in Sage",
    "HOPE_SAGE_PRIVATE_GAP": "Private billing in Hope vs Sage revenue", "SAGE_INVOICES_UNLINKED": "Sage invoices not matched to receipts",
    "INACTIVE_WITH_BALANCE": "Inactive account with a balance",
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _upsert(conn, e: str, kind: str, key: str, seen: set, *, title: str, summary: str, severity: str, amount: Any = None,
            quantity: Any = None, as_of: Optional[dt.date] = None, detail: Optional[Dict[str, Any]] = None) -> None:
    seen.add((kind, key))
    ex(conn, """INSERT INTO fin_data_issues (legal_entity_id, kind, key, title, summary, severity, amount, quantity, as_of, detail)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (legal_entity_id, kind, key) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary,
                    severity=EXCLUDED.severity, amount=EXCLUDED.amount, quantity=EXCLUDED.quantity, as_of=EXCLUDED.as_of,
                    detail=EXCLUDED.detail, last_seen=now(),
                    status = CASE WHEN fin_data_issues.status='RESOLVED' AND fin_data_issues.resolution='cleared by data'
                                  THEN 'OPEN' ELSE fin_data_issues.status END,
                    resolution = CASE WHEN fin_data_issues.status='RESOLVED' AND fin_data_issues.resolution='cleared by data'
                                      THEN NULL ELSE fin_data_issues.resolution END""",
       (e, kind, key, title, summary, severity, amount, quantity, as_of, jsonb(json.loads(json.dumps(detail or {}, default=str)))))


def _history_as_of(conn, e: str) -> Optional[dt.date]:
    r = q1(conn, "SELECT as_of FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key='import-log'", (e,))
    return r["as_of"] if r else None


def _tb_history(conn, e: str, seen: set) -> None:
    h = _history_as_of(conn, e)
    tb = q1(conn, "SELECT rows FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key='trial-balance'", (e,))
    if not h or not tb:
        return
    sage: Dict[str, Decimal] = {}
    for r in tb["rows"] or []:
        if r and r[0] and str(r[0]).strip().replace(".", "").replace("-", "").isalnum() and len(r) >= 4:
            try:
                sage[str(r[0]).strip()] = money(r[2] or 0) - money(r[3] or 0)
            except ValueError:
                continue
    hist = {r["code"]: (money(r["bal"]), money(r["ytd"]), r["account_type"], r["subtype"]) for r in q(conn, """
        SELECT a.code, a.account_type, a.subtype, COALESCE(SUM(g.debit-g.credit) FILTER (WHERE g.journal_type <> 'CLOSING'),0) bal,
               COALESCE(SUM(g.debit-g.credit) FILTER (WHERE g.journal_date >= %s AND g.journal_type <> 'CLOSING'),0) ytd
        FROM fin_accounts a LEFT JOIN fin_v_ledger g ON g.account_id=a.id AND g.journal_date <= %s
        WHERE a.legal_entity_id=%s GROUP BY a.code, a.account_type, a.subtype""", (dt.date(h.year, 1, 1), h, e))}
    for code, sb in sage.items():
        if code not in hist:
            continue
        bal, ytd, atype, sub = hist[code]
        if sub in ("RETAINED_EARNINGS", "EQUITY_CLOSING"):
            continue   # Sage closes prior years' results into these without journal lines
        ours = ytd if atype in ("REVENUE", "EXPENSE") else bal
        if ours != sb:
            _upsert(conn, e, "TB_HISTORY", code, seen, title=f"Account {code}: history differs from Sage's trial balance",
                    summary=f"Sage ₦{sb:,.2f} at {h:%d %b %Y}; the ledger ₦{ours:,.2f}", severity="HIGH", amount=ours - sb, as_of=h,
                    detail={"account": code, "sage": sb, "ledger": ours})


def _history_gap(conn, e: str, seen: set) -> None:
    h = _history_as_of(conn, e)
    s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (e,)) or {}
    if not h or s.get("cutover_date"):
        return
    hope = q1(conn, """SELECT MAX(charge_date) d, COALESCE(SUM(gross-discount),0) billed, COUNT(*) n FROM fin_v_hope_charges
                       WHERE charge_date > %s AND payer_type <> 'INTERNAL'""", (h,))
    if not hope["n"]:
        return
    _upsert(conn, e, "HISTORY_GAP", f"after-{h}", seen, title=f"No books after {h:%d %b %Y}",
            summary=(f"Sage's history ends {h:%d %b %Y}; Hope billed ₦{money(hope['billed']):,.2f} after it (to {hope['d']:%d %b %Y}) "
                     "that no ledger records yet. Upload the next Sage export (Setup › Sage uploads), then set the go-live date."),
            severity="HIGH", amount=money(hope["billed"]), as_of=h, detail={"history_until": h, "hope_until": hope["d"], "lines": hope["n"]})


def _stock(conn, e: str, seen: set) -> None:
    from src.fin import hospital
    r = hospital.stock_reconciliation(conn, e)
    sh = r["shelf"]
    if not r["opening_stock_loaded"] and money(sh["value"]) > 0:
        _upsert(conn, e, "INVENTORY_OPENING", "pharmacy", seen, title="Pharmacy stock is not in the books",
                summary=(f"The pharmacy holds ₦{money(sh['value']):,.2f} ({sh['lines']} batches); the ledger's inventory accounts show "
                         f"₦{r['ledger_total']:,.2f}. Royan's Sage expensed drugs when bought. Load the opening stock at go-live."),
                severity="HIGH", amount=money(sh["value"]), quantity=sh["lines"], as_of=r["as_of"],
                detail={"ledger_total": r["ledger_total"], "books_value": r["books_value"], "shelf": sh})
    if sh["no_cost"]:
        rows = q(conn, """SELECT b.id, COALESCE(f.generic_name, f.brand_name) AS product, b.batch_number, b.quantity_on_hand
                          FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                          WHERE b.quantity_on_hand > 0 AND COALESCE(b.unit_cost,0) <= 0 ORDER BY 2""")
        _upsert(conn, e, "STOCK_NO_COST", "pharmacy", seen, title=f"{sh['no_cost']} batches on the shelf have no unit cost",
                summary="They cannot be valued, so they cannot enter the books as opening stock. Enter the cost in Pharmacy › Inventory.",
                severity="MEDIUM", quantity=sh["no_cost"], as_of=r["as_of"], detail={"batches": rows[:200]})
    if sh["expired"]:
        rows = q(conn, """SELECT b.id, COALESCE(f.generic_name, f.brand_name) AS product, b.batch_number, b.expiry_date,
                                 b.quantity_on_hand, b.quantity_on_hand * COALESCE(b.unit_cost,0) AS value
                          FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                          WHERE b.quantity_on_hand > 0 AND b.expiry_date < CURRENT_DATE ORDER BY b.expiry_date""")
        _upsert(conn, e, "STOCK_EXPIRED", "pharmacy", seen, title=f"{sh['expired']} expired batches are still on the shelf",
                summary=f"₦{money(sh['expired_value']):,.2f} at cost. Write them off or return them to the supplier.",
                severity="MEDIUM", amount=money(sh["expired_value"]), quantity=sh["expired"], as_of=r["as_of"], detail={"batches": rows})


def _payers(conn, e: str, seen: set) -> None:
    for p in q(conn, """SELECT p.tariff_id, p.name, p.payer_type, SUM(c.outstanding) billed, MIN(c.charge_date) first, MAX(c.charge_date) last
                        FROM fin_hope_payers p JOIN fin_hope_charges c ON c.payer_tariff_id=p.tariff_id
                        WHERE p.payer_type IN ('HMO','CORPORATE')
                          AND NOT EXISTS (SELECT 1 FROM fin_hope_payer_accounts a WHERE a.tariff_id=p.tariff_id)
                        GROUP BY p.tariff_id HAVING SUM(c.outstanding) >= %s""", (MIN_PAYER_BILLED,)):
        _upsert(conn, e, "PAYER_NO_SAGE_ACCOUNT", str(p["tariff_id"]), seen, title=f"{p['name']}: billed in Hope, no Sage account",
                summary=(f"Hope left ₦{money(p['billed']):,.2f} for this {p['payer_type'].lower()} payer to pay "
                         f"({p['first']:%b %Y} – {p['last']:%b %Y}), but no Sage account is linked, so nothing it paid can be "
                         "set against it. Link its Sage account, or re-type it if it is not a credit payer."),
                severity="MEDIUM", amount=money(p["billed"]), detail={"payer_id": p["tariff_id"], "payer_type": p["payer_type"]})
    h = _history_as_of(conn, e)
    if not h:
        return
    for p in q(conn, """WITH b AS (SELECT c.payer_tariff_id t, SUM(c.outstanding) billed FROM fin_v_hope_charges c
                                   WHERE c.payer_type IN ('HMO','CORPORATE') AND c.charge_date <= %s GROUP BY 1),
                             i AS (SELECT a.tariff_id t, SUM(s.amount) invoiced FROM fin_sage_invoices s
                                   JOIN fin_hope_payer_accounts a ON a.customer_id=s.customer_id
                                   WHERE s.legal_entity_id=%s AND s.invoice_date >= (SELECT MIN(charge_date) FROM fin_hope_charges)
                                   GROUP BY 1)
                        SELECT p.tariff_id, p.name, p.customer_id, b.billed, COALESCE(i.invoiced,0) invoiced
                        FROM b JOIN i ON i.t=b.t JOIN fin_hope_payers p ON p.tariff_id=b.t
                        WHERE b.billed - COALESCE(i.invoiced,0) > GREATEST(%s, b.billed * 0.10)""", (h, e, MIN_PAYER_BILLED)):
        gap = money(p["billed"]) - money(p["invoiced"])
        _upsert(conn, e, "HMO_BILLED_NOT_INVOICED", str(p["tariff_id"]), seen,
                title=f"{p['name']}: ₦{gap:,.0f} billed in Hope, not invoiced in Sage",
                summary=(f"To {h:%d %b %Y} Hope billed ₦{money(p['billed']):,.2f} to this payer's members; Sage invoiced it "
                         f"₦{money(p['invoiced']):,.2f}. The difference is care never claimed - or claimed outside Sage."),
                severity="MEDIUM", amount=gap, as_of=h, detail={"payer_id": p["tariff_id"], "customer_id": p["customer_id"],
                                                                 "billed": p["billed"], "invoiced": p["invoiced"]})


def _private_gap(conn, e: str, seen: set) -> None:
    h = _history_as_of(conn, e)
    if not h:
        return
    for r in q(conn, """WITH hp AS (SELECT extract(year FROM charge_date)::int y, SUM(gross-discount) billed FROM fin_v_hope_charges
                                    WHERE payer_type IN ('PRIVATE','STAFF') AND charge_date <= %s GROUP BY 1),
                              sp AS (SELECT extract(year FROM journal_date)::int y, SUM(credit-debit) rev FROM fin_v_ledger
                                     WHERE legal_entity_id=%s AND subtype='SALES' AND account_code <> '4050'
                                       AND journal_type NOT IN ('OPENING','CLOSING') GROUP BY 1)
                         SELECT hp.y, hp.billed, sp.rev FROM hp JOIN sp USING (y)
                         WHERE hp.y > (SELECT extract(year FROM MIN(charge_date)) FROM fin_hope_charges)""", (h, e)):
        billed, rev = money(r["billed"]), money(r["rev"])
        if billed and abs(billed - rev) > billed * PRIVATE_GAP_TOLERANCE:
            sc = money(q1(conn, """SELECT COALESCE(SUM(gross-discount),0) v FROM fin_v_hope_charges WHERE payer ILIKE 'scancare%%'
                                   AND payer_type='PRIVATE' AND extract(year FROM charge_date)=%s""", (r["y"],))["v"])
            _upsert(conn, e, "HOPE_SAGE_PRIVATE_GAP", str(r["y"]), seen,
                    title=f"{r['y']}: private billing in Hope ₦{billed:,.0f} vs Sage revenue ₦{rev:,.0f}",
                    summary=(f"A ₦{billed - rev:,.2f} difference. ₦{sc:,.2f} of Hope's figure is Scancare's walk-in customers; "
                             "the rest is billing never booked as revenue in Sage (or booked under another head). "
                             "Open Hope vs Sage reconciliation for the months."),
                    severity="MEDIUM", amount=billed - rev, as_of=dt.date(r["y"], 12, 31),
                    detail={"year": r["y"], "hope_billed": billed, "sage_revenue": rev, "scancare": sc})


def _sage_unlinked(conn, e: str, seen: set) -> None:
    r = q1(conn, """SELECT COUNT(*) n, COALESCE(SUM(amount-amount_received),0) v FROM fin_sage_invoices
                    WHERE legal_entity_id=%s AND amount - amount_received > 0.005""", (e,))
    ar = q1(conn, """SELECT COALESCE(SUM(g.debit-g.credit),0) v FROM fin_v_ledger g
                     JOIN fin_account_mappings m ON m.account_id=g.account_id AND m.mapping_key='AR_CONTROL' AND m.legal_entity_id=g.legal_entity_id
                     WHERE g.legal_entity_id=%s AND g.origin='SAGE'""", (e,))
    if r["n"]:
        _upsert(conn, e, "SAGE_INVOICES_UNLINKED", "all", seen, title=f"{r['n']} Sage invoices show a balance Sage itself does not",
                summary=(f"₦{money(r['v']):,.2f} on invoices whose receipt named a different invoice number; Sage's receivables "
                         f"control shows ₦{money(ar['v']):,.2f}. Nothing is owed - the receipts are linked to the wrong numbers."),
                severity="LOW", amount=money(r["v"]), quantity=r["n"], detail={"ar_control": ar["v"]})


def _inactive(conn, e: str, seen: set) -> None:
    for a in q(conn, """SELECT a.id::text AS id, a.code, a.name, SUM(g.debit-g.credit) bal FROM fin_accounts a
                        JOIN fin_v_ledger g ON g.account_id=a.id WHERE a.legal_entity_id=%s AND a.status <> 'ACTIVE'
                          AND a.account_type NOT IN ('REVENUE','EXPENSE')
                        GROUP BY a.id HAVING SUM(g.debit-g.credit) <> 0""", (e,)):
        _upsert(conn, e, "INACTIVE_WITH_BALANCE", a["code"], seen, title=f"Account {a['code']} {a['name']} is inactive with a balance",
                summary=f"It carries ₦{money(a['bal']):,.2f}. Reactivate it, or move the balance with a correcting journal.",
                severity="LOW", amount=money(a["bal"]), detail={"account_id": a["id"], "account": a["code"]})


CHECKS: List[Callable] = [_tb_history, _history_gap, _stock, _payers, _private_gap, _sage_unlinked, _inactive]


def refresh(conn, ctx) -> Dict[str, Any]:
    e = ctx.entity_id
    seen: set = set()
    for check in CHECKS:
        check(conn, e, seen)
    gone = 0
    for x in q(conn, "SELECT id, kind, key FROM fin_data_issues WHERE legal_entity_id=%s AND status='OPEN'", (e,)):
        if (x["kind"], x["key"]) not in seen:
            ex(conn, """UPDATE fin_data_issues SET status='RESOLVED', resolution='cleared by data', resolved_by='system',
                        resolved_at=now() WHERE id=%s""", (x["id"],))
            gone += 1
    audit.record(conn, ctx, "DATA_ISSUES_CHECKED", "data_issues", e, metadata={"found": len(seen), "cleared": gone})
    return {**summary(conn, e), "cleared": gone}


def summary(conn, e: str) -> Dict[str, Any]:
    rows = q(conn, """SELECT kind, status, COUNT(*) n, COALESCE(SUM(amount),0) amount FROM fin_data_issues
                      WHERE legal_entity_id=%s GROUP BY 1,2""", (e,))
    return {"open": sum(r["n"] for r in rows if r["status"] == "OPEN"),
            "by_kind": [{**r, "label": TITLES.get(r["kind"], r["kind"])} for r in rows],
            "last_checked": (q1(conn, "SELECT MAX(last_seen) t FROM fin_data_issues WHERE legal_entity_id=%s", (e,)) or {}).get("t")}


def list_issues(conn, e: str, status: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    w, p = ["legal_entity_id=%s"], [e]
    if status:
        w.append("status = ANY(%s)")
        p.append(status.split(","))
    if kind:
        w.append("kind=%s")
        p.append(kind)
    rows = q(conn, f"""SELECT id::text AS id, kind, key, title, summary, severity, amount, quantity, as_of, status, resolution,
                              resolution_note, resolved_by, resolved_at, first_seen, last_seen
                       FROM fin_data_issues WHERE {' AND '.join(w)}
                       ORDER BY CASE status WHEN 'OPEN' THEN 0 ELSE 1 END,
                                CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, abs(COALESCE(amount,0)) DESC""", p)
    for r in rows:
        r["kind_label"] = TITLES.get(r["kind"], r["kind"])
    return rows


def get(conn, e: str, issue_id: str) -> Dict[str, Any]:
    x = q1(conn, "SELECT * FROM fin_data_issues WHERE id=%s AND legal_entity_id=%s", (issue_id, e))
    if not x:
        raise not_found("Data issue", issue_id)
    x["kind_label"] = TITLES.get(x["kind"], x["kind"])
    x["actions"] = q(conn, """SELECT a.*, j.journal_number FROM fin_data_issue_actions a LEFT JOIN fin_journals j ON j.id=a.journal_id
                              WHERE a.issue_id=%s ORDER BY a.created_at""", (issue_id,))
    x["options"] = _options(x)
    x["links"] = _links(x)
    return x


def _links(x: Dict[str, Any]) -> List[Dict[str, str]]:
    d = x.get("detail") or {}
    k = x["kind"]
    if k == "TB_HISTORY":
        return [{"label": "Tie-out report", "to": "/finance/books/reports?r=ess-tie"}]
    if k == "HISTORY_GAP":
        return [{"label": "Upload the next Sage export", "to": "/finance/books/setup?tab=sage-uploads"}]
    if k == "INVENTORY_OPENING":
        return [{"label": "Stock: ledger vs books vs shelf", "to": "/finance/books/stock?tab=reconciliation"},
                {"label": "Load opening stock (at go-live)", "to": "/finance/books/setup?tab=migration"}]
    if k in ("STOCK_NO_COST", "STOCK_EXPIRED"):
        return [{"label": "Stock counts", "to": "/finance/books/stock?tab=counts"}, {"label": "Pharmacy inventory", "to": "/inventory"}]
    if k == "PAYER_NO_SAGE_ACCOUNT":
        return [{"label": "Setup › Payers", "to": "/finance/books/setup?tab=payers"},
                {"label": "The payer's bills", "to": f"/finance/books/reports?r=hmo-monthly-bill&payer={d.get('payer_id')}&from=2016-01-01"}]
    if k == "HMO_BILLED_NOT_INVOICED":
        return [{"label": "HMO billing: Hope vs Sage", "to": "/finance/books/reports?r=hmo-billing-reconciliation"}]
    if k == "HOPE_SAGE_PRIVATE_GAP":
        y = d.get("year")
        return [{"label": f"Hope vs Sage {y}", "to": f"/finance/books/reports?r=hope-sage-reconciliation&from={y}-01-01&to={y}-12-31"}]
    if k == "SAGE_INVOICES_UNLINKED":
        return [{"label": "Invoice register (open)", "to": "/finance/books/sales?tab=register&status=open"}]
    if k == "INACTIVE_WITH_BALANCE":
        return [{"label": "Chart of accounts", "to": "/finance/books/ledger?tab=coa"}]
    return []


def _options(x: Dict[str, Any]) -> List[Dict[str, str]]:
    if x["status"] != "OPEN":
        return [{"action": "reopen", "label": "Reopen"}]
    opts = []
    if x["kind"] == "PAYER_NO_SAGE_ACCOUNT":
        opts.append({"action": "link_account", "label": "Link its Sage account"})
    if x["kind"] in ("TB_HISTORY", "HMO_BILLED_NOT_INVOICED", "INACTIVE_WITH_BALANCE"):
        opts.append({"action": "post_correction", "label": "Post a correcting journal"})
    opts.append({"action": "accept", "label": "Accept as it is"})
    return opts


# ---------------------------------------------------------------------------
# Resolutions
# ---------------------------------------------------------------------------

def _log(conn, ctx, x: Dict[str, Any], action: str, *, note: Optional[str], payload: Dict[str, Any],
         journal_id: Optional[str] = None, reference: Optional[str] = None) -> None:
    ex(conn, """INSERT INTO fin_data_issue_actions (issue_id, legal_entity_id, action, reference, note, payload, journal_id, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
       (x["id"], ctx.entity_id, action, reference, note, jsonb(json.loads(json.dumps(payload, default=str))), journal_id,
        ctx.actor_name or ctx.actor_id))
    audit.record(conn, ctx, f"DATA_ISSUE_{action.upper()}", "data_issue", x["id"], ref=x["title"], reason=note)


def _close(conn, ctx, x: Dict[str, Any], status: str, resolution: str, note: Optional[str]) -> None:
    ex(conn, """UPDATE fin_data_issues SET status=%s, resolution=%s, resolution_note=%s, resolved_by=%s, resolved_at=now()
                WHERE id=%s""", (status, resolution, note, ctx.actor_name or ctx.actor_id, x["id"]))


def resolve(conn, ctx, issue_id: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    x = q1(conn, "SELECT * FROM fin_data_issues WHERE id=%s AND legal_entity_id=%s FOR UPDATE", (issue_id, ctx.entity_id))
    if not x:
        raise not_found("Data issue", issue_id)
    note = (data.get("note") or data.get("reason") or "").strip() or None
    if action == "reopen":
        ctx.require("controls.run")
        ex(conn, """UPDATE fin_data_issues SET status='OPEN', resolution=NULL, resolution_note=NULL, resolved_by=NULL,
                    resolved_at=NULL WHERE id=%s""", (issue_id,))
        _log(conn, ctx, x, "reopen", note=note, payload={})
    elif x["status"] != "OPEN":
        raise FinError("INVALID_STATE_TRANSITION", "This issue is already closed; reopen it first")
    elif action == "accept":
        ctx.require("controls.run")
        if not note:
            raise invalid("Say why it is accepted as it is")
        _log(conn, ctx, x, "accept", note=note, payload={})
        _close(conn, ctx, x, "ACCEPTED", "accepted", note)
    elif action == "link_account":
        ctx.require("finance.settings.edit")
        cid = data.get("customer_id")
        if x["kind"] != "PAYER_NO_SAGE_ACCOUNT" or not cid:
            raise invalid("Choose the payer's Roy Books / Sage account")
        t = int((x["detail"] or {})["payer_id"])
        ex(conn, """INSERT INTO fin_hope_payer_accounts (customer_id, tariff_id, match_method, linked_by)
                    VALUES (%s,%s,'linked by hand',%s) ON CONFLICT (customer_id) DO UPDATE SET tariff_id=EXCLUDED.tariff_id,
                    match_method=EXCLUDED.match_method, linked_by=EXCLUDED.linked_by""", (int(cid), t, ctx.actor_id))
        ex(conn, "UPDATE fin_hope_payers SET customer_id=COALESCE(customer_id, %s) WHERE tariff_id=%s", (int(cid), t))
        _log(conn, ctx, x, "link_account", note=note, payload={"customer_id": cid})
        _close(conn, ctx, x, "RESOLVED", "linked to its Sage account", note)
    elif action == "post_correction":
        ctx.require("accounting.journal.create")
        if not note:
            raise invalid("Say what the correction is for")
        lines = data.get("lines") or []
        if len(lines) < 2:
            raise invalid("A correcting journal needs at least two lines")
        on = data.get("journal_date") or x["as_of"] or _history_as_of(conn, ctx.entity_id) or dt.date.today()
        if isinstance(on, str):
            on = dt.date.fromisoformat(on[:10])
        ref = next_number(conn, ctx.entity_id, "DATA_CORRECTION")
        j = posting.post_system(conn, ctx, event_type="DATA_CORRECTION_POSTED", journal_date=on,
                                lines=[{**l, "description": l.get("description") or f"{ref} {x['title']}"} for l in lines],
                                description=f"{ref} - {x['title']}: {note}", source_type="DATA_CORRECTION", source_id=x["id"],
                                source_ref=ref, journal_type="ADJUSTMENT")
        _log(conn, ctx, x, "post_correction", note=note, payload={"lines": lines, "date": on}, journal_id=str(j["id"]), reference=ref)
        if data.get("close", True):
            _close(conn, ctx, x, "RESOLVED", f"corrected by {ref}", note)
    else:
        raise invalid(f"Unknown action {action}")
    return get(conn, ctx.entity_id, issue_id)
