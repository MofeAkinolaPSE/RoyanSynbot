"""Flow tests for the reportGUide.md modules (s15): each test runs the real hub services against the
real schema inside ONE connection that is rolled back at the end - nothing is left in the database.

fin.db.pinned() routes every tx() through that connection (as savepoints), migration 225 is applied
inside it (a no-op once applied for real), and audit_event is captured instead of written.

From the dev host (Royan's DB container publishes 5433):
    FIN_TEST_DATABASE_URL=postgresql://postgres:<pw>@localhost:5433/synbot_health JWT_SECRET=<32+ chars> \\
        python -m pytest tests/flows -q -p no:cacheprovider
"""
import os
import re
import uuid
from pathlib import Path

import pytest

if os.environ.get("FIN_TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["FIN_TEST_DATABASE_URL"]

from src.db import db  # noqa: E402
from src.fin.db import pinned, q1  # noqa: E402

STATE = {"migration_applied": True}
MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "225_report_guide_modules.sql"


@pytest.fixture
def conn(monkeypatch):
    c = db.pool.getconn()
    c.autocommit = False
    audits = []
    import src.db as srcdb
    monkeypatch.setattr(srcdb, "audit_event", lambda *a, **k: audits.append((a, k)))
    try:
        applied = q1(c, """SELECT 1 FROM information_schema.columns
                           WHERE table_name='royan_replenishment_requests' AND column_name='expected_date'""")
        if not applied:
            # Applied inside this rolled-back transaction. Its ALTER TABLE holds a lock until rollback, so a
            # service that reads that table through ANOTHER pooled connection would wait on us forever -
            # tests marked `needs_applied_migration` are skipped until 225 is applied for real.
            sql = re.sub(r"(?m)^\s*(BEGIN|COMMIT);\s*$", "", MIGRATION.read_text(encoding="utf-8"))
            with c.cursor() as cur:
                cur.execute(sql)
        STATE["migration_applied"] = bool(applied)
        with pinned(c):
            yield c
    finally:
        c.rollback()
        db.pool.putconn(c)


def user(*roles, sub=None):
    return {"sub": sub or str(uuid.uuid4()), "roles": list(roles)}


@pytest.fixture
def make_user(conn):
    """A throwaway login (rolled back) - never a real person's account."""
    def _make(*roles):
        email = f"flow-{uuid.uuid4().hex[:10]}@example.test"
        r = q1(conn, "INSERT INTO royan_users (email, hashed_password, roles, is_active) VALUES (%s,'x',%s,true) RETURNING id::text AS id",
               (email, list(roles) or ["viewer"]))
        return {"sub": r["id"], "roles": list(roles), "email": email}
    return _make


@pytest.fixture
def make_drug(conn):
    """A throwaway formulary item with optional stock (rolled back) - never a real drug's batches."""
    def _make(qty=0, unit_cost=100, expiry=None):
        code = "FLOW-" + uuid.uuid4().hex[:8].upper()
        f = q1(conn, """INSERT INTO royan_drug_formulary (code, generic_name, form, strength, unit_cost, is_active)
                        VALUES (%s, %s, 'tablet', '10mg', %s, true) RETURNING id""", (code, f"Flowtestamine {code}", unit_cost))
        if qty:
            q1(conn, """INSERT INTO royan_inventory_batches (formulary_id, batch_number, quantity_on_hand, quantity_received, unit_cost, expiry_date)
                        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""", (f["id"], "B-" + code, qty, qty, unit_cost, expiry))
        return f["id"]
    return _make


def needs_applied_migration():
    """Skip a test whose services read the altered tables through other pooled connections."""
    if not STATE["migration_applied"]:
        pytest.skip("apply migrations/225_report_guide_modules.sql first - in-transaction DDL would block other connections")
