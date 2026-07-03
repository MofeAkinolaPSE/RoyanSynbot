"""Guards against the Python STAFF_ROLES list and the DB chk_staff_role CHECK
constraint (migration 144) silently drifting apart — the only two places the
canonical role vocabulary is allowed to live.

Requires a real Postgres connection (DATABASE_URL); skipped otherwise since
there is no way to introspect a live CHECK constraint against a mocked DB.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.constants import STAFF_ROLES  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set; cannot introspect live CHECK constraint")
def test_staff_role_check_constraint_matches_constants():
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'chk_staff_role' AND conrelid = 'public.royan_staff'::regclass"
            )
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, "chk_staff_role constraint not found — has migration 144 been applied?"
    constraint_def = row[0]
    db_roles = set(re.findall(r"'([a-z_]+)'::text", constraint_def))
    assert db_roles == set(STAFF_ROLES), (
        f"DB chk_staff_role and constants.STAFF_ROLES have drifted apart.\n"
        f"DB only:     {db_roles - set(STAFF_ROLES)}\n"
        f"Python only: {set(STAFF_ROLES) - db_roles}"
    )
