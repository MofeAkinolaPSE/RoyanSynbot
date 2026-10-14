"""Link Hope's appointment slots to the doctor they belong to (re-runnable).

Hope stored the doctor on each slot as its own numeric user id (e.g. "209"), which this system
imported as royan_appointment_slots.doctor_name. Nothing could therefore show a doctor "their"
appointments. This resolves each code to the doctor's name through Hope's users table (in the
staging copy), matches the name to the doctor's HR record (royan_staff, same rule as staff
onboarding: titles and word order ignored), and stores:

    doctor_id         the HR record, when exactly one doctor matches
    doctor_name       the real name instead of the number
    hope_doctor_code  the original code (migration 227), so the link can be reviewed or undone

Run on the host (reading the 19 GB staging file through a container mount is far slower):
    DATABASE_URL=postgresql://postgres:<pw>@localhost:5433/synbot_health \
        python scripts/link_slot_doctors.py --staging ../data-assimilation/staging/hope_staging.db [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET", "link-slot-doctors-script-not-used-for-auth-000000")

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

from src.services.staff_onboarding import _name_score  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    lite = sqlite3.connect(f"file:{a.staging}?mode=ro", uri=True)
    users = {}
    for (raw,) in lite.execute("SELECT data FROM raw_hope_users"):
        u = json.loads(raw)
        users[str(u["id"])] = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x).strip()

    pg = psycopg2.connect(os.environ["DATABASE_URL"])
    pg.autocommit = False
    cur = pg.cursor(cursor_factory=RealDictCursor)
    cur.execute("""SELECT trim(doctor_name) AS code, COUNT(*) AS n FROM royan_appointment_slots
                   WHERE doctor_name ~ '^\\s*[0-9]+\\s*$' AND hope_doctor_code IS NULL GROUP BY 1""")
    codes = cur.fetchall()
    cur.execute("""SELECT id::text AS id, full_name FROM royan_staff
                   WHERE role='doctor' AND quarantined_at IS NULL""")
    doctors = cur.fetchall()

    linked = named = unknown = 0
    report = []
    for c in codes:
        name = users.get(c["code"])
        if not name:
            unknown += c["n"]
            report.append((c["code"], c["n"], "-", "no Hope user with this id"))
            continue
        scored = sorted(((_name_score(name, d["full_name"]), d) for d in doctors), key=lambda x: -x[0])
        best = [d for s, d in scored if s >= 0.85 and s == scored[0][0]]
        staff = best[0]["id"] if len(best) == 1 else None
        if staff:
            linked += c["n"]
        else:
            named += c["n"]
        report.append((c["code"], c["n"], name, best[0]["full_name"] if staff else ("ambiguous" if len(best) > 1 else "not in HR")))
        if not a.dry_run:
            cur.execute("""UPDATE royan_appointment_slots SET hope_doctor_code=%s, doctor_name=%s, doctor_id=%s
                           WHERE trim(doctor_name)=%s AND hope_doctor_code IS NULL""", (c["code"], name, staff, c["code"]))
    for r in sorted(report, key=lambda r: -r[1])[:40]:
        print(f"{r[0]:>6} {r[1]:>7}  {r[2][:30]:<30} -> {r[3]}")
    print(f"\nslots linked to an HR doctor: {linked:,} | named but not linked: {named:,} | unknown code: {unknown:,}")
    if a.dry_run:
        pg.rollback()
        print("dry run - nothing written")
    else:
        pg.commit()
        print("written")


if __name__ == "__main__":
    main()
