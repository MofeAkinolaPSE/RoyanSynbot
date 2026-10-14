"""Patient Relations (s7) and the calendar over records (s10)."""
import datetime as dt

import pytest

from src.fin.db import q1
from src.services import hospital_calendar as cal
from src.services import payer_relations as pr
from .conftest import user


def _busiest_payer():
    d = pr.directory()
    assert d["payers"], "no HMO / corporate payers loaded"
    return d, d["payers"][0]


def test_directory_segments_and_debt_agree_with_credit_control(conn):
    from src.fin import credit
    d, top = _busiest_payer()
    assert set(d["counts"]) == {"active", "new", "lapsing", "lapsed", "never_billed"}
    assert sum(d["counts"].values()) == len(d["payers"])
    for p in d["payers"]:
        assert p["payer_type"] in ("HMO", "CORPORATE")
        assert p["at_risk"] == bool(p["risk_reasons"])
    # what a payer owes is Credit Control's figure, not a second calculation
    debt = {r["payer_id"]: float(r["total_balance"]) for r in credit._debtors_cached()["rows"] if r.get("payer_id")}
    for p in d["payers"][:20]:
        assert round(p["owed"], 2) == round(debt.get(p["id"], 0.0), 2)


def test_contact_follow_up_reaches_my_day_and_closes(conn, make_user):
    _, top = _busiest_payer()
    me = make_user("finance")
    before = pr.overview()["follow_ups_due"]
    with pytest.raises(pr.RelationsError):
        pr.log_contact(me, top["id"], {"kind": "call", "summary": "x", "follow_up_on": "2000-01-01"})
    with pytest.raises(pr.RelationsError):
        pr.log_contact(me, top["id"], {"kind": "call", "summary": "  "})
    cid = pr.log_contact(me, top["id"], {"kind": "call", "summary": "Chased December claims",
                                         "follow_up_on": dt.date.today().isoformat()})["id"]
    assert pr.overview()["follow_ups_due"] == before + 1
    assert [f["id"] for f in pr.follow_ups_due(me["sub"])] == [cid]
    from src.services.staff_workspace import RULE_BY_KEY
    items = RULE_BY_KEY["relations.follow_ups"]["fn"](me)
    assert any(i["id"] == cid and i["link"].startswith("/relations") for i in items)
    pr.complete_follow_up(me, cid)
    assert pr.follow_ups_due(me["sub"]) == []
    prof = pr.profile(top["id"])
    assert prof["contacts"][0]["summary"] == "Chased December claims"
    with pytest.raises(LookupError):
        pr.profile(-1)


def test_calendar_shows_records_by_role_and_moving_moves_the_record(conn):
    day = dt.date.today() + dt.timedelta(days=10)
    aid = q1(conn, """INSERT INTO royan_facility_audits (audit_title, department, scheduled_date)
                      VALUES ('Flow test audit', 'Flow ward', %s) RETURNING id::text AS id""", (day,))["id"]
    ops = user("ops")
    f = cal.feed(ops, dt.date.today(), dt.date.today() + dt.timedelta(days=30))
    ev = next(e for e in f["events"] if e["source"] == "audit" and e["id"] == aid)
    assert ev["movable"] and ev["date"] == day
    nurse_sources = {s["key"] for s in cal.feed(user("nurse"), dt.date.today(), day)["sources"]}
    assert "audit" not in nurse_sources and "appointment" in nurse_sources
    with pytest.raises(PermissionError):
        cal.reschedule(user("nurse"), "audit", aid, day)
    with pytest.raises(ValueError):
        cal.reschedule(ops, "audit", aid, dt.date.today() - dt.timedelta(days=1))
    with pytest.raises(ValueError):
        cal.reschedule(ops, "appointment", "1", day)          # moved on its own page
    new = day + dt.timedelta(days=3)
    cal.reschedule(ops, "audit", aid, new)
    assert q1(conn, "SELECT scheduled_date FROM royan_facility_audits WHERE id::text=%s", (aid,))["scheduled_date"] == new
    with pytest.raises(ValueError):
        cal.feed(ops, dt.date.today(), dt.date.today() + dt.timedelta(days=200))
