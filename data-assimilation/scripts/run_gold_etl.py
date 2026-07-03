"""Gold Layer ETL — CLI entry point. Blueprint Chapter 12.

Loads silver data into the four fact tables and computes daily KPI
snapshots for a given date. Idempotent — safe to re-run for the same
date (existing rows are skipped, KPIs are upserted).

Usage:
  cd data-assimilation
  python scripts/run_gold_etl.py
  python scripts/run_gold_etl.py --date 2026-06-27
  python scripts/run_gold_etl.py --date 2026-06-27 --dry-run
  python scripts/run_gold_etl.py --help
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date

# Allow running from data-assimilation/ or from the repo root
_DA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DA_DIR not in sys.path:
    sys.path.insert(0, _DA_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gold_etl_cli")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYY-MM-DD.")


def _resolve_db_url(cli_url: str) -> str:
    if cli_url:
        return cli_url
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    env_path = os.path.join(_DA_DIR, ".env")
    if os.path.isfile(env_path):
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        dest="run_date",
        type=_parse_date,
        default=date.today(),
        metavar="YYYY-MM-DD",
        help="Date to load (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report row counts without writing to the database",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="PostgreSQL connection URL (default: $DATABASE_URL env var or .env file)",
    )
    args = parser.parse_args()

    database_url = _resolve_db_url(args.database_url)
    if not database_url:
        log.error("DATABASE_URL not set. Use --database-url or set it in data-assimilation/.env")
        sys.exit(1)

    print()
    print("=" * 64)
    print("  SYNBOT HEALTH — GOLD LAYER ETL")
    print("=" * 64)
    print(f"  Date     : {args.run_date}")
    print(f"  Dry run  : {'YES — no writes' if args.dry_run else 'NO — will write'}")
    print(f"  Database : {database_url[:50]}...")
    print("=" * 64)
    print()

    import psycopg2
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
    except Exception as exc:
        log.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    from loaders.gold_etl import run_gold_etl

    t0 = time.perf_counter()
    try:
        summary = run_gold_etl(conn, run_date=args.run_date, dry_run=args.dry_run)
    finally:
        conn.close()

    elapsed = time.perf_counter() - t0

    print()
    print("=" * 64)
    print("  RESULTS")
    print("=" * 64)
    for table, result in summary["tables"].items():
        status_icon = "✓" if result["status"] == "ok" else "✗"
        print(f"  {status_icon} {table:<35} {result['rows']:>6} rows  [{result['status']}]")
        if result.get("error"):
            print(f"      Error: {result['error']}")
    print("-" * 64)
    print(f"  Overall  : {summary['overall_status'].upper()}")
    print(f"  Duration : {elapsed:.2f}s")
    print("=" * 64)
    print()

    if summary["errors"]:
        log.error("%d table(s) failed. See errors above.", len(summary["errors"]))
        sys.exit(1)

    print("Gold ETL completed successfully.")


if __name__ == "__main__":
    main()
