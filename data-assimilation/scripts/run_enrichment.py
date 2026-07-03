"""DrM Enrichment Backfill — Blueprint Phase 7.

Populates FK columns that were added in migrations 131 and 132.
Run AFTER the main ingest.py (or pipeline.py) has finished loading all
primary entities (patients, encounters, lab, pharmacy, billing).

MDM master tables (royan_departments, royan_staff, royan_lab_catalog,
royan_drug_formulary, royan_hmos) must be seeded first — either by running
migration 130 (which seeds defaults) or by running master_loader.py.

Enrichment passes (run in order by default):
  enc:dept          encounters.department_id   ← department text → royan_departments
  enc:doctor        encounters.doctor_id        ← consulting_doctor text → royan_staff
  lab:catalog       lab_orders.catalog_id       ← test_code → royan_lab_catalog
  lab:ordered-by    lab_orders.ordered_by_id    ← ordered_by text → royan_staff
  rx:prescribed-by  prescriptions.prescribed_by_id ← prescribed_by → royan_staff
  billing:hmo       billing.hmo_id + claims.hmo_id ← patient hmo_provider → royan_hmos
  discharge:records INSERT royan_discharge_records from discharged encounters

Usage:
  cd data-assimilation
  python scripts/run_enrichment.py
  python scripts/run_enrichment.py --dry-run
  python scripts/run_enrichment.py --passes enc:dept enc:doctor
  python scripts/run_enrichment.py --passes discharge:records --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# Allow running from data-assimilation/ or root
_DA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DA_DIR not in sys.path:
    sys.path.insert(0, _DA_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrichment")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--passes",
        nargs="+",
        metavar="PASS",
        help="Enrichment passes to run. Default: all. Choices: enc:dept enc:doctor "
             "lab:catalog lab:ordered-by rx:prescribed-by billing:hmo discharge:records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts without writing anything to the database",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL (default: $DATABASE_URL env var)",
    )
    args = parser.parse_args()

    database_url = args.database_url
    if not database_url:
        # Fall back to .env file in data-assimilation/
        env_path = os.path.join(_DA_DIR, ".env")
        if os.path.isfile(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not database_url:
        log.error(
            "DATABASE_URL not set. Use --database-url or set it in data-assimilation/.env"
        )
        sys.exit(1)

    from loaders.enrichment_loader import ALL_PASSES, run_all_passes
    import psycopg2

    passes = args.passes or ALL_PASSES
    unknown = [p for p in passes if p not in ALL_PASSES]
    if unknown:
        log.error("Unknown passes: %s. Valid: %s", unknown, ALL_PASSES)
        sys.exit(1)

    print()
    print("=" * 64)
    print("  SYNBOT HEALTH — DrM ENRICHMENT BACKFILL")
    print("=" * 64)
    print(f"  Database : {database_url[:40]}...")
    print(f"  Passes   : {', '.join(passes)}")
    print(f"  Dry run  : {'YES — no writes' if args.dry_run else 'NO — will write'}")
    print("=" * 64)
    print()

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
    except Exception as exc:
        log.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    t0 = time.perf_counter()

    try:
        results = run_all_passes(conn, passes, dry_run=args.dry_run)
    finally:
        conn.close()

    elapsed = round(time.perf_counter() - t0, 1)

    print()
    print("=" * 64)
    print("  ENRICHMENT RESULTS")
    print("=" * 64)

    all_ok = True
    for pass_name, result in results.items():
        if isinstance(result, str) and "FAILED" in result:
            print(f"  {pass_name:<22} FAILED — {result}")
            all_ok = False
        elif isinstance(result, dict):
            # Format key metrics for display
            updated = result.get("updated") or result.get("inserted") or result.get("billing_updated") or 0
            matched = result.get("matched") or result.get("candidates") or result.get("billing_matched") or 0
            unmatched = result.get("unmatched") or result.get("unmatched_patients") or 0
            skipped = result.get("skipped") or result.get("bare_integers_skipped") or 0

            parts = [f"matched={matched}", f"updated={updated}"]
            if unmatched:
                parts.append(f"unmatched={unmatched}")
            if skipped:
                parts.append(f"skipped={skipped}")
            print(f"  {pass_name:<22} {', '.join(parts)}")
        else:
            print(f"  {pass_name:<22} {result}")

    print()
    print(f"  Completed in {elapsed}s")
    print("=" * 64)
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
