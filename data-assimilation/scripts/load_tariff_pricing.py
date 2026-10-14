"""Load Hope's general tariff grid: base prices + per-payer rates.

THE POLYMORPHIC KEY
-------------------
tariff_amounts.tariff_list_id does not always point at tariff_lists. It is
polymorphic, discriminated by service_category_id:

    category 3  (Radiology)  -> radiologies.id     7,519 priced rows, 100% resolve
    category 26 (Laboratory) -> laboratories.id    9,584 priced rows,  74% resolve
    anything else            -> tariff_lists.id    6,872 priced rows

This was found only because the 17,401 "unresolvable" rows were is_deleted='0'
with recent create_times, which contradicted the obvious explanation that they
referenced deleted services. Resolution goes 28% -> 88% as a result.

BASE PRICE
----------
Hope has an explicit self-pay tariff: tariff_standard_id = 7, "Private". That is
the real list price, and it is used wherever it exists (247 of 271 lab tests,
334 of 434 services).

Radiology has NO Private row (0 of 211), so its base price is the modal price
across payers -- the most commonly agreed figure, not an average, because the
distribution has a long tail and a mean would be dragged by outliers. The
migration records that this column is an approximation.

Usage:
    python scripts/load_tariff_pricing.py --dry-run
    python scripts/load_tariff_pricing.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("load_tariff_pricing")

STAGING = str(Path(__file__).resolve().parent.parent / "staging" / "hope_staging.db")
PRIVATE_STANDARD = "7"          # Hope's self-pay tariff
CAT_RADIOLOGY = "3"
CAT_LABORATORY = "26"


def _rows(conn, table):
    for (blob,) in conn.execute('SELECT data FROM "%s"' % table):
        yield json.loads(blob)


def _charge(r):
    v = (r.get("non_nabh_charges") or "").strip()
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def build():
    conn = sqlite3.connect(STAGING)
    tl = {int(r["id"]) for r in _rows(conn, "raw_hope_tariff_lists") if str(r.get("id", "")).isdigit()}
    lab = {int(r["id"]) for r in _rows(conn, "raw_hope_laboratories") if str(r.get("id", "")).isdigit()}
    rad = {int(r["id"]) for r in _rows(conn, "raw_hope_radiologies") if str(r.get("id", "")).isdigit()}
    amounts = [r for r in _rows(conn, "raw_hope_tariff_amounts")
               if _charge(r) > 0 and (r.get("is_deleted") or "0") != "1"]
    conn.close()

    def kind(r):
        lid = int(r.get("tariff_list_id") or 0)
        cat = r.get("service_category_id")
        if cat == CAT_RADIOLOGY and lid in rad:
            return "radiology"
        if cat == CAT_LABORATORY and lid in lab:
            return "lab"
        if lid in tl:
            return "service"
        return None

    resolved = [(kind(r), r) for r in amounts]
    log.info("priced tariff rows: %d", len(amounts))
    log.info("  by target: %s", Counter(k or "UNRESOLVED" for k, _ in resolved).most_common())

    # --- per-payer rates: one per (target, payer) ---------------------------
    #
    # "Latest Hope id wins" looked obvious and is wrong. General Ward carries
    # two Private rows created the SAME DAY -- N3,000 and N200 -- so id order
    # picks N200 for a ward day. create_time cannot break the tie either.
    #
    # Only 131 of 21,245 groups (0.6%) disagree at all, but where they do the
    # spread is severe (median 6.7x, worst 1000x). Taking the highest charge is
    # the safer default for billing: under-charging an HMO is harder to correct
    # after the fact than over-charging, which shows up immediately. The
    # ambiguous groups are counted and reported rather than silently resolved.
    grouped = defaultdict(list)
    for k, r in resolved:
        if not k:
            continue
        grouped[(k, int(r["tariff_list_id"]), r.get("tariff_standard_id"))].append(r)

    rates = {}
    ambiguous = 0
    for key, rows in grouped.items():
        if len({_charge(r) for r in rows}) > 1:
            ambiguous += 1
        rates[key] = max(rows, key=_charge)
    log.info("deduped per-payer rates: %d", len(rates))
    if ambiguous:
        log.warning(
            "%d of %d (target,payer) groups had CONFLICTING charges; took the highest. "
            "Worth a human eye before these drive billing.", ambiguous, len(grouped))

    # --- base prices --------------------------------------------------------
    private = {}
    for (k, lid, std), r in rates.items():
        if std == PRIVATE_STANDARD:
            private[(k, lid)] = _charge(r)
    log.info("Private (self-pay) base prices: %d", len(private))

    # Radiology has no Private tariff; use the modal price across payers.
    by_target = defaultdict(list)
    for (k, lid, _std), r in rates.items():
        by_target[(k, lid)].append(_charge(r))
    modal = {}
    for key, vals in by_target.items():
        if key in private:
            continue
        modal[key] = Counter(vals).most_common(1)[0][0]
    log.info("modal fallback base prices: %d (radiology has no Private tariff)", len(modal))

    base = dict(private)
    base.update(modal)

    return {
        "rates": [
            {"kind": k, "hope_target_id": lid, "hope_payer_id": std,
             "price": _charge(r), "external_id": str(r["id"])}
            for (k, lid, std), r in rates.items()
        ],
        "base": [
            {"kind": k, "hope_target_id": lid, "price": p,
             "basis": "private" if (k, lid) in private else "modal"}
            for (k, lid), p in base.items()
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    payload = build()
    rates, base = payload["rates"], payload["base"]

    print("")
    print("per-payer rates ready : %d" % len(rates))
    print("base prices ready     : %d  (private %d / modal %d)" % (
        len(base),
        sum(1 for b in base if b["basis"] == "private"),
        sum(1 for b in base if b["basis"] == "modal")))
    print("  by kind: %s" % Counter(b["kind"] for b in base).most_common())

    if args.dry_run:
        print("")
        print("DRY RUN - nothing written. Sample base prices:")
        for b in base[:6]:
            print("   %-10s hope_id=%-6s N%-12s (%s)" % (
                b["kind"], b["hope_target_id"], "{:,.2f}".format(b["price"]), b["basis"]))
        print("")
        print("Re-run with --execute to load.")
        return

    from loaders.db_loader import load_tariff_pricing, get_conn  # noqa: E402
    dsn = os.getenv("DATABASE_URL") or "postgresql://postgres:postgres@localhost:5432/synbot_health"
    conn = get_conn(dsn)
    try:
        result = load_tariff_pricing(conn, rates, base)
        print("")
        print(result)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
