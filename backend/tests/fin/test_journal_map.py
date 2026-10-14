"""Journals by type, Delete entry, number release, assets from payments - the Oct 2026 implementation standard.

Real schema, throwaway entity, one rolled-back transaction (see conftest.py).
"""
import datetime as dt
import os
import re
from decimal import Decimal

from src.fin import assets, banking, journal_map, journals, numbering, posting
from src.fin.db import ex, q, q1

FIN = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def test_every_posting_source_has_a_journal():
    """Every source_type handed to post_system somewhere in the code is in the table (no silent GENJ fallback)."""
    found = set()
    for root, _, files in os.walk(FIN):
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(root, f), encoding="utf-8").read()
                for m in re.finditer(r"post_system\((.*?)\)\n", src, re.S):
                    found |= set(re.findall(r'source_type="([A-Z_]+)"', m.group(1)))
    assert found, "no postings found"
    missing = sorted(found - set(journal_map.SOURCE_JOURNAL))
    assert not missing, f"source types without a journal: {missing}"


def test_every_code_is_listed_in_exactly_one_journal_report():
    codes = set(journal_map.SOURCE_JOURNAL.values()) | set(journal_map.VOUCHER_JOURNAL.values())
    for code in codes:
        owners = [k for k, c in journal_map.KEY_CODE.items() if code in journal_map.report_codes(c)]
        assert len(owners) == 1, (code, owners)


def test_sql_and_python_journal_codes_agree(conn):
    for st, code in journal_map.SOURCE_JOURNAL.items():
        if st == "CASH_VOUCHER":
            continue
        got = q1(conn, "SELECT fin_journal_code(%s, NULL) c", (st,))["c"]
        assert got == code, (st, got, code)
    assert q1(conn, "SELECT fin_journal_code('SOMETHING_NEW', NULL) c")["c"] == journal_map.DEFAULT


def _bank(conn, ctx):
    return q1(conn, "SELECT id, gl_account_id FROM fin_bank_accounts WHERE legal_entity_id=%s LIMIT 1", (ctx.entity_id,))


def _setup(conn, make_entity):
    ctx, a = make_entity()
    bank = _bank(conn, ctx) or banking.create_account(conn, ctx, {"name": "Test bank", "gl_account_id": str(a["10290"]["id"])})
    return ctx, a, bank


def test_vouchers_land_in_their_own_journal(conn, make_entity):
    ctx, a, bank = _setup(conn, make_entity)
    d = dt.date(2026, 3, 10)
    spend = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "Mr Test",
                                               "lines": [{"account_id": str(a["62200"]["id"]), "amount": "1500"}]})
    rec = banking.create_voucher(conn, ctx, {"kind": "RECEIVE", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "Someone",
                                             "lines": [{"account_id": str(a["40800"]["id"]), "amount": "700"}]})
    cdj = journals.journal(conn, ctx.entity_id, "cash-disbursements", d, d)
    crj = journals.journal(conn, ctx.entity_id, "cash-receipts", d, d)
    assert {r["journal_id"] for r in cdj["rows"]} == {spend["journal_id"]}
    assert {r["journal_id"] for r in crj["rows"]} == {rec["journal_id"]}
    assert cdj["total_debit"] == cdj["total_credit"] == Decimal("1500.00")
    line = q1(conn, "SELECT jrnl FROM fin_v_ledger WHERE journal_id=%s LIMIT 1", (rec["journal_id"],))
    assert line["jrnl"] == "CRJ"   # the ledger's Jrnl column says the same


def test_delete_entry_hides_the_pair_but_every_balance_returns(conn, make_entity):
    ctx, a = make_entity()
    d = dt.date(2026, 4, 2)
    before = journals.account_ledger(conn, ctx.entity_id, str(a["62200"]["id"]), dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    j = posting.create_manual(conn, ctx, journal_date=d, description="Test furniture",
                              lines=[{"account_id": str(a["62200"]["id"]), "debit": "200000"},
                                     {"account_id": str(a["10290"]["id"]), "credit": "200000"}])
    posting.post_manual(conn, ctx, str(j["id"]))
    mid = journals.account_ledger(conn, ctx.entity_id, str(a["62200"]["id"]), dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert mid["closing"] == before["closing"] + Decimal("200000")
    posting.reverse(conn, ctx, str(j["id"]), reversal_date=None, reason="Deleted: posted by mistake")
    after = journals.account_ledger(conn, ctx.entity_id, str(a["62200"]["id"]), dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert after["closing"] == before["closing"]
    assert not any(l["journal_id"] == j["id"] for m in after["months"] for l in m["lines"])   # hidden from ledger detail
    assert q1(conn, "SELECT status FROM fin_journals WHERE id=%s", (j["id"],))["status"] == "REVERSED"   # still in Journal entries


def test_a_voided_last_document_gives_its_number_back(conn, make_entity):
    ctx, a, bank = _setup(conn, make_entity)
    d = dt.date(2026, 5, 5)
    first = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "A",
                                               "lines": [{"account_id": str(a["62200"]["id"]), "amount": "100"}]})
    num = first["voucher_number"]
    banking.void_voucher(conn, ctx, str(first["id"]), "keyed twice")
    assert q1(conn, "SELECT voucher_number FROM fin_cash_vouchers WHERE id=%s", (first["id"],))["voucher_number"] == f"{num}-VOID"
    again = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "A",
                                               "lines": [{"account_id": str(a["62200"]["id"]), "amount": "100"}]})
    assert again["voucher_number"] == num            # reissued
    banking.void_voucher(conn, ctx, str(again["id"]), "again")
    assert q1(conn, "SELECT voucher_number FROM fin_cash_vouchers WHERE id=%s", (again["id"],))["voucher_number"] == f"{num}-VOID-2"
    third = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "B",
                                               "lines": [{"account_id": str(a["62200"]["id"]), "amount": "100"}]})
    fourth = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "C",
                                                "lines": [{"account_id": str(a["62200"]["id"]), "amount": "100"}]})
    banking.void_voucher(conn, ctx, str(third["id"]), "not the last one")
    assert q1(conn, "SELECT voucher_number FROM fin_cash_vouchers WHERE id=%s", (third["id"],))["voucher_number"] == third["voucher_number"]
    assert fourth["voucher_number"] != third["voucher_number"]


def test_an_asset_paid_by_voucher_is_registered_once_without_a_second_journal(conn, make_entity):
    ctx, a, bank = _setup(conn, make_entity)
    from src.fin import accounts
    fa = accounts.create_account(conn, ctx, {"code": "15000", "name": "Furniture", "subtype": "FIXED_ASSET"})
    ad = accounts.create_account(conn, ctx, {"code": "17000", "name": "Accum dep furniture", "subtype": "ACCUMULATED_DEPRECIATION"})
    de = accounts.create_account(conn, ctx, {"code": "68000", "name": "Depreciation", "subtype": "OPERATING_EXPENSE"})
    cat = q1(conn, """INSERT INTO fin_asset_categories (legal_entity_id, code, name, asset_account_id, accum_dep_account_id,
                      dep_expense_account_id, depreciable, default_life_months) VALUES (%s,'FURN','Furniture',%s,%s,%s,TRUE,60)
                      RETURNING id""", (ctx.entity_id, fa["id"], ad["id"], de["id"]))
    d = dt.date(2026, 6, 1)
    v = banking.create_voucher(conn, ctx, {"kind": "SPEND", "voucher_date": d, "bank_account_id": str(bank["id"]), "payee": "Mr Mufe",
                                           "lines": [{"account_id": str(fa["id"]), "amount": "200000", "description": "Chairs"}]})
    n_journals = q1(conn, "SELECT COUNT(*) n FROM fin_journals WHERE legal_entity_id=%s", (ctx.entity_id,))["n"]
    asset = assets.register_asset(conn, ctx, {"name": "Chairs", "category_id": str(cat["id"]), "acquisition_date": d, "cost": "200000",
                                              "useful_life_months": 60, "funding": "POSTED", "source_line": f"voucher:{v['id']}:1"})
    assert q1(conn, "SELECT COUNT(*) n FROM fin_journals WHERE legal_entity_id=%s", (ctx.entity_id,))["n"] == n_journals
    hist = assets.asset_history(conn, ctx.entity_id, dt.date(2026, 12, 31))
    acct = next(x for x in hist["accounts"] if x["code"] == "15000")
    assert acct["cost"] == Decimal("200000.00") and len(acct["purchases"]) == 1
    import pytest
    from src.fin.errors import FinError
    with pytest.raises(FinError):
        assets.register_asset(conn, ctx, {"name": "Chairs", "category_id": str(cat["id"]), "acquisition_date": d, "cost": "200000",
                                          "useful_life_months": 60, "funding": "POSTED", "source_line": f"voucher:{v['id']}:1"})
    assert asset["asset_code"]
