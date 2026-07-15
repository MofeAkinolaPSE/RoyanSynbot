"""Data Lineage Engine — ETL Coverage Report.

Run on demand:
    python lineage/coverage_report.py                 # summary to stdout
    python lineage/coverage_report.py --json out.json # full registry to file

Answers "did every Hope column end up somewhere?" with hard numbers per
entity: how many observed source columns were mapped vs. ignored, plus the
top ignored columns worth reviewing for a future backfill.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
from config import STAGING_DB_PATH  # noqa: E402
from lineage.mapping_registry import build_registry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", metavar="PATH", help="write the full registry as JSON to this path")
    parser.add_argument("--staging-db", default=STAGING_DB_PATH)
    args = parser.parse_args()

    registry = build_registry(args.staging_db)

    print("=" * 72)
    print("HOPE -> SYNBOT ETL FIELD COVERAGE REPORT")
    print("=" * 72)

    entities = sorted({r["entity"] for r in registry})
    grand = Counter()
    for entity in entities:
        rows = [r for r in registry if r["entity"] == entity]
        counts = Counter(r["status"] for r in rows)
        grand.update(counts)
        observed = counts["mapped"] + counts["ignored"]
        pct = round(counts["mapped"] / observed * 100, 1) if observed else 0.0
        print(f"\n{entity}")
        print(f"  observed Hope columns : {observed}")
        print(f"  mapped                : {counts['mapped']} ({pct}%)")
        print(f"  ignored (left behind) : {counts['ignored']}")
        print(f"  unmatched map entries : {counts['unmatched']} (aliases never seen in dump)")
        ignored = [r["hope_column"] for r in rows if r["status"] == "ignored"]
        if ignored:
            preview = ", ".join(ignored[:10])
            more = f" ... +{len(ignored) - 10} more" if len(ignored) > 10 else ""
            print(f"  ignored columns       : {preview}{more}")

    observed_total = grand["mapped"] + grand["ignored"]
    overall = round(grand["mapped"] / observed_total * 100, 1) if observed_total else 0.0
    print("\n" + "=" * 72)
    print(f"OVERALL: {grand['mapped']}/{observed_total} observed Hope columns mapped ({overall}%)")
    print("=" * 72)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, indent=2)
        print(f"\nFull registry written to {args.json}")


if __name__ == "__main__":
    main()
