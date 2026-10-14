"""A later trial balance (finance's reconciled year-end) brings every account to finance's figures once the books
are already open: the difference is posted, not a second opening."""
import datetime as dt
import uuid
from decimal import Decimal

from src.fin import migration, posting
from src.fin.db import q, q1


def _batch(as_of, rows):
    return {"id": str(uuid.uuid4()), "as_of_date": as_of,
            "rows": [{"code": c, "name": c, "debit": Decimal(str(d)), "credit": Decimal(str(cr))} for c, d, cr in rows]}


def _balances(conn, entity_id, date_from, date_to):
    return {r["code"]: Decimal(str(r["bal"])) for r in q(conn, """SELECT account_code AS code, SUM(debit-credit) AS bal
                FROM fin_v_ledger WHERE legal_entity_id=%s AND journal_date BETWEEN %s AND %s GROUP BY 1""",
                                                           (entity_id, date_from, date_to))}


def test_later_trial_balance_trues_up_every_account(conn, make_entity):
    ctx, a = make_entity()
    first = migration._load_tb(conn, ctx, _batch(dt.date(2026, 1, 1), [("10100", 1000, 0), ("39005", 0, 1000)]))
    assert first["journal"]
    j = posting.create_manual(conn, ctx, journal_date=dt.date(2026, 3, 1), description="Cash sale",
                              lines=[{"account_id": a["10100"]["id"], "debit": 500}, {"account_id": a["40000"]["id"], "credit": 500}])
    posting.post_manual(conn, ctx, j["id"])

    # finance's reconciled figures at 30 June: more cash, a bank balance, a supplier owed, more sales
    tb = _batch(dt.date(2026, 6, 30), [("10100", 1800, 0), ("10290", 200, 0), ("20000", 0, 100),
                                       ("40000", 0, 900), ("39005", 0, 1000)])
    res = migration._load_tb(conn, ctx, tb)
    assert res["true_up"] and Decimal(res["history_gap"]) == 0
    bal = _balances(conn, ctx.entity_id, dt.date(2000, 1, 1), dt.date(2026, 6, 30))
    assert bal["10100"] == 1800 and bal["10290"] == 200 and bal["20000"] == -100
    assert bal["40000"] == -900 and bal["39005"] == -1000
    assert q1(conn, """SELECT journal_type, source_ref FROM fin_journals WHERE legal_entity_id=%s AND source_id=%s""",
              (ctx.entity_id, tb["id"])) == {"journal_type": "ADJUSTMENT", "source_ref": "TB-TRUE-UP"}

    # loading the same file again is refused; a trial balance the books already match posts nothing
    try:
        migration._load_tb(conn, ctx, tb)
        assert False, "second load of the same trial balance should be refused"
    except Exception as e:
        assert "already loaded" in str(e)
    same = migration._load_tb(conn, ctx, _batch(dt.date(2026, 6, 30), [("10100", 1800, 0), ("10290", 200, 0), ("20000", 0, 100),
                                                                       ("40000", 0, 900), ("39005", 0, 1000)]))
    assert same["journal"] is None
