"""Sage closes income, expense and "Equity - gets closed" accounts into retained earnings at each year end. The ledger
never posts those closings, so the statements and the Sage-layout General Ledger must show them the way Sage prints
them (tied to Royan's own Sage GL: retained earnings -510,617,303.50 and Capital's in Bank nil at 31 Dec 2024)."""
import datetime as dt
from decimal import Decimal

from src.fin import accounts, journals, periods, posting, reports


def test_closed_equity_and_prior_profit_roll_into_retained_earnings(conn, make_entity):
    ctx, a = make_entity()
    periods.create_fiscal_year(conn, ctx, dt.date(2025, 1, 1))
    a["3940"] = accounts.create_account(conn, ctx, {"code": "3940", "name": "Capital's in Bank", "subtype": "EQUITY_CLOSING"})

    def jv(d, dr, cr, amt):
        j = posting.create_manual(conn, ctx, journal_date=d, description="t",
                                  lines=[{"account_id": a[dr]["id"], "debit": amt}, {"account_id": a[cr]["id"], "credit": amt}])
        posting.post_manual(conn, ctx, j["id"])

    jv(dt.date(2025, 6, 1), "10100", "3940", 2000)     # equity that Sage closes at year end
    jv(dt.date(2025, 7, 1), "10100", "40000", 500)     # 2025 profit
    jv(dt.date(2026, 3, 1), "10100", "40000", 300)     # 2026 profit
    re_id = str(a["39005"]["id"])

    led = journals.account_ledger(conn, ctx.entity_id, re_id, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert led["opening"] == Decimal("-2500.00")                      # 2025 profit + closed equity, as Sage shows
    closing = journals.account_ledger(conn, ctx.entity_id, str(a["3940"]["id"]), dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert closing["opening"] == 0 and closing["closing"] == 0         # closed into retained earnings
    span = journals.account_ledger(conn, ctx.entity_id, re_id, dt.date(2025, 1, 1), dt.date(2026, 12, 31))
    assert span["closing"] == Decimal("-2500.00")                       # takes in 2025 at the turn of the year

    bs = reports.balance_sheet(conn, ctx.entity_id, dt.date(2026, 12, 31))
    assert bs["balanced"]
    assert not any(l.get("code") == "3940" for l in bs["equity"]["lines"])
    names = {l["name"]: l["amount"] for l in bs["equity"]["lines"]}
    assert names["Retained earnings brought forward (prior years not closed in the ledger)"] == Decimal("2500.00")
    assert names["Current year earnings (not yet closed)"] == Decimal("300.00")
    re = reports.retained_earnings(conn, ctx.entity_id, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert re["opening"] == Decimal("2500.00") and re["closing"] == Decimal("2800.00")
