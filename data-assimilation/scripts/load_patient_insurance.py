"""Load Hope's new_insurances into royan_patient_insurance.

WHY
---
The client raised this in BOTH staff meetings: the HMO dashboard shows no
insurance numbers. It shows none because royan_patient_insurance has 0 rows --
not because the data is missing. Hope's `new_insurances` (162,991 rows) was
staged months ago and never loaded.

THE KEY IS NOT WHAT ITS NAME SAYS
---------------------------------
`new_insurances.patient_uid` sounds like an MRN. It is not: it holds
`persons.id`. Measured against the staged data:

    patient_uid -> persons.patient_uid (the MRN)  ...      0 / 18,126
    patient_uid -> persons.id                     ... 18,126 / 18,126  (100%)

So the resolution chain is:

    new_insurances.patient_uid
      -> persons.id
      -> patients.person_id
      -> patients.patient_id      (the MRN, e.g. RH16-1030)
      -> royan_patients.mrn

Trusting the column name would have loaded exactly zero rows while reporting
success, which is the failure mode check_yield() exists to catch.

WHAT ACTUALLY LOADS
-------------------
162,991 raw rows carry ~4 historical revisions per patient. Deduplicated to the
latest row per (patient, payer) that has a real membership number:

    21,776 (patient, payer) pairs across 18,126 patients

`priority` is the literal 'P' on all 162,991 rows so it cannot mark the primary
policy, and royan_patient_insurance permits ONE primary active policy per
patient. This loader therefore marks the single most recent policy per patient
as primary and loads the rest as non-primary history.

Usage:
    python scripts/load_patient_insurance.py --dry-run
    python scripts/load_patient_insurance.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Three Phase A loads failed silently for want of this one line.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("load_patient_insurance")

STAGING = str(Path(__file__).resolve().parent.parent / "staging" / "hope_staging.db")


def _rows(conn, table):
    for (blob,) in conn.execute('SELECT data FROM "%s"' % table):
        yield json.loads(blob)


def build_payload():
    """Resolve the chain in memory and return rows ready for insert."""
    conn = sqlite3.connect(STAGING)

    # persons.id -> MRN, via patients.person_id
    mrn_by_person = {}
    for p in _rows(conn, "raw_patients"):
        pid, mrn = p.get("person_id"), p.get("patient_id")
        if pid and mrn and pid not in mrn_by_person:
            mrn_by_person[pid] = mrn
    log.info("person_id -> MRN entries: %d", len(mrn_by_person))

    # Latest Hope row per (patient, payer) that carries a real number.
    best = {}
    total = 0
    no_number = 0
    for r in _rows(conn, "raw_hope_new_insurances"):
        total += 1
        number = (r.get("insurance_number") or "").strip()
        if not number:
            no_number += 1
            continue
        key = (r.get("patient_uid"), r.get("tariff_standard_id"))
        prev = best.get(key)
        if prev is None or int(r["id"]) > int(prev["id"]):
            best[key] = r
    conn.close()

    log.info("raw rows: %d (%d carried no membership number)", total, no_number)
    log.info("deduped (patient, payer) pairs: %d", len(best))

    # One primary per patient: the highest Hope id across that patient's payers.
    primary_id_by_patient = {}
    for (uid, _payer), r in best.items():
        cur = primary_id_by_patient.get(uid)
        if cur is None or int(r["id"]) > int(cur):
            primary_id_by_patient[uid] = int(r["id"])

    payload = []
    unresolved = 0
    for (uid, payer), r in best.items():
        mrn = mrn_by_person.get(uid)
        if not mrn:
            unresolved += 1
            continue
        payload.append({
            "external_id": str(r["id"]),
            "mrn": mrn,
            "hope_payer_id": payer,
            "membership_id": (r.get("insurance_number") or "").strip(),
            # Hope's `status` is Pending/Closed, which is a claims-workflow
            # state, not whether the policy is live. Mapping Closed -> inactive
            # is the only defensible reading; everything else stays active.
            "status": "inactive" if (r.get("status") or "").lower() == "closed" else "active",
            "is_primary": int(r["id"]) == primary_id_by_patient.get(uid),
            "notes": (r.get("note") or "").strip() or None,
        })

    log.info("resolved to an MRN: %d (unresolved %d)", len(payload), unresolved)
    log.info("distinct patients: %d", len({p["mrn"] for p in payload}))
    log.info("marked primary: %d", sum(1 for p in payload if p["is_primary"]))
    return payload


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    payload = build_payload()

    if args.dry_run:
        print("")
        print("DRY RUN - nothing written. Sample of what would load:")
        for p in payload[:5]:
            print("   MRN=%-11s payer=%-5s number=%-22s primary=%s status=%s" % (
                p["mrn"], p["hope_payer_id"], p["membership_id"], p["is_primary"], p["status"]))
        print("")
        print("Rows ready: %d" % len(payload))
        print("Re-run with --execute to load.")
        return

    # Imported late so a dry run needs no DB connection.
    import os
    from loaders.db_loader import load_patient_insurance, get_conn  # noqa: E402

    dsn = (
        os.getenv("DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/synbot_health"
    )
    conn = get_conn(dsn)
    try:
        seen, upserted = load_patient_insurance(conn, payload)
        print("")
        print("seen %d, upserted %d" % (seen, upserted))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
