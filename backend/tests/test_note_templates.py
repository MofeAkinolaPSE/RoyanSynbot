"""Doctor-authored note templates: visibility, ownership and validation.

Runs the route functions against an in-memory table store, so nothing touches
the real database."""
from __future__ import annotations

import asyncio
import itertools
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.routers import clinical_docs as cd  # noqa: E402

ME = "11111111-1111-1111-1111-111111111111"
COLLEAGUE = "22222222-2222-2222-2222-222222222222"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.filters, self.action, self.payload, self._limit = [], "select", None, None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in set(vals))
        return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%").lower()
        self.filters.append(lambda r: needle in str(r.get(col) or "").lower())
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def _match(self):
        return [r for r in self.store[self.table] if all(f(r) for f in self.filters)]

    def execute(self):
        rows = self.store[self.table]
        if self.action == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in items:
                row = {"id": next(self.store["_ids"]), **item}
                rows.append(row)
                out.append(row)
            return _Result(out)
        if self.action == "update":
            hit = self._match()
            for r in hit:
                r.update(self.payload)
            return _Result(hit)
        if self.action == "delete":
            hit = self._match()
            self.store[self.table] = [r for r in rows if r not in hit]
            return _Result(hit)
        hit = self._match()
        return _Result(hit[: self._limit] if self._limit else hit)


class FakeDB:
    def __init__(self):
        self.store = {cd.TABLE_NOTE_TEMPLATES: [], cd.TABLE_NOTE_TEMPLATE_TEXTS: [], "_ids": itertools.count(1)}

    def table(self, name):
        return _Query(self.store, name)

    def seed(self, **tpl):
        row = {"is_active": True, "is_shared": True, "scope": "personal", "category": None,
               "department": None, "owner_staff_id": None, **tpl}
        row["id"] = next(self.store["_ids"])
        self.store[cd.TABLE_NOTE_TEMPLATES].append(row)
        return row


@pytest.fixture()
def fake(monkeypatch):
    db = FakeDB()
    staff = {"doc@royan.ng": {"id": ME}, "colleague@royan.ng": {"id": COLLEAGUE}}
    monkeypatch.setattr(cd, "db", db)
    monkeypatch.setattr(cd, "get_staff_by_email", lambda email: staff.get(email))
    monkeypatch.setattr(cd, "audit_event", lambda *a, **k: None)
    return db


DOCTOR = {"sub": "u-me", "email": "doc@royan.ng", "roles": ["doctor"]}
COLLEAGUE_DOCTOR = {"sub": "u-c", "email": "colleague@royan.ng", "roles": ["doctor"]}
NURSE = {"sub": "u-n", "email": "nurse@royan.ng", "roles": ["nurse"]}


def run(coro):
    return asyncio.run(coro)


def body(name="Antenatal review", shared=False, **phrases):
    phrases = phrases or {"subjective": ["Pain in the ?? knee"], "plan": ["Review in ?? weeks"]}
    return cd.NoteTemplateWrite(
        name=name,
        is_shared=shared,
        phrases=[cd.NoteTemplatePhrase(context_type=k, text=t) for k, ts in phrases.items() for t in ts],
    )


def listing(user, **kw):
    params = {"context_type": None, "scope": None, "q": None, "mine": False, "limit": 200, **kw}
    return run(cd.list_note_templates(user=user, **params))["templates"]


def test_doctor_creates_a_private_template_only_they_see(fake):
    res = run(cd.create_note_template(body(), user=DOCTOR))
    assert res["phrases"] == 2 and res["template"]["is_mine"]

    mine = listing(DOCTOR, context_type="plan")
    assert [t["name"] for t in mine] == ["Antenatal review"] and mine[0]["is_mine"]
    assert listing(COLLEAGUE_DOCTOR) == []
    texts = run(cd.list_note_template_texts(res["template"]["id"], context_type=None, limit=300, user=COLLEAGUE_DOCTOR))
    assert texts["texts"] == [], "a private template's phrases must not leak by id"


def test_shared_template_is_visible_to_colleagues_but_not_theirs(fake):
    run(cd.create_note_template(body(shared=True), user=DOCTOR))
    seen = listing(COLLEAGUE_DOCTOR)
    assert len(seen) == 1 and seen[0]["is_mine"] is False


def test_migrated_templates_stay_visible(fake):
    fake.seed(name="SK/AK/SQ Cancer", scope="system", is_shared=True)
    fake.seed(name="Dr A's HPI", scope="personal", is_shared=True, owner_staff_id=None)
    assert {t["name"] for t in listing(NURSE)} == {"SK/AK/SQ Cancer", "Dr A's HPI"}


def test_only_doctors_can_author(fake):
    with pytest.raises(HTTPException) as e:
        run(cd.create_note_template(body(), user=NURSE))
    assert e.value.status_code == 403


def test_unlinked_login_gets_a_clear_message(fake):
    with pytest.raises(HTTPException) as e:
        run(cd.create_note_template(body(), user={"sub": "x", "email": "ghost@royan.ng", "roles": ["doctor"]}))
    assert e.value.status_code == 400 and "staff record" in e.value.detail


def test_duplicate_name_and_bad_section_rejected(fake):
    run(cd.create_note_template(body(), user=DOCTOR))
    with pytest.raises(HTTPException) as e:
        run(cd.create_note_template(body(name="  antenatal   REVIEW "), user=DOCTOR))
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        run(cd.create_note_template(body(name="Other", vitals=["x"]), user=DOCTOR))
    assert e.value.status_code == 422


def test_update_replaces_phrases_and_only_owner_may(fake):
    tid = run(cd.create_note_template(body(), user=DOCTOR))["template"]["id"]
    with pytest.raises(HTTPException) as e:
        run(cd.update_note_template(tid, body(name="Hijack"), user=COLLEAGUE_DOCTOR))
    assert e.value.status_code == 403

    run(cd.update_note_template(tid, body(name="ANC v2", shared=True, assessment=["Normal pregnancy"]), user=DOCTOR))
    texts = [r for r in fake.store[cd.TABLE_NOTE_TEMPLATE_TEXTS] if r["template_id"] == tid]
    assert [(t["context_type"], t["text"]) for t in texts] == [("assessment", "Normal pregnancy")]
    assert listing(COLLEAGUE_DOCTOR)[0]["name"] == "ANC v2"


def test_system_templates_are_read_only(fake):
    sys_tpl = fake.seed(name="Shared hospital template", scope="system")
    with pytest.raises(HTTPException) as e:
        run(cd.delete_note_template(sys_tpl["id"], user={**DOCTOR, "roles": ["admin"]}))
    assert e.value.status_code == 403


def test_delete_hides_template_but_keeps_the_row(fake):
    tid = run(cd.create_note_template(body(), user=DOCTOR))["template"]["id"]
    run(cd.delete_note_template(tid, user=DOCTOR))
    assert listing(DOCTOR) == []
    assert any(r["id"] == tid and r["is_active"] is False for r in fake.store[cd.TABLE_NOTE_TEMPLATES])
