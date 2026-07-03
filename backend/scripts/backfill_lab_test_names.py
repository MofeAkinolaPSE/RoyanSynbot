"""Backfill missing test names for lab orders imported from Hope.

Two resolution strategies:
  1. --from-catalog (default, recommended):
       Joins royan_lab_orders.test_code → royan_lab_catalog.code to resolve
       the real test name. Requires the MDM lab catalog to be loaded first
       (via data-assimilation --entity master).

  2. --from-bridge:
       Re-fetches the original record from the Hope Bridge API and updates
       the test_name in-place (original strategy, requires live bridge).

Usage:
    python scripts/backfill_lab_test_names.py [--dry-run] [--from-bridge] [--batch 200]

Flags:
    --dry-run       Print what would be updated without writing to the DB.
    --from-bridge   Use Hope Bridge API instead of local lab catalog.
    --batch N       How many Hope Bridge records to fetch per call (default 200).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import psycopg2
import psycopg2.extras

from src.constants import (
    HOPE_BRIDGE_KEY,
    HOPE_BRIDGE_TIMEOUT_SECONDS,
    HOPE_BRIDGE_URL,
    TABLE_LAB_ORDERS,
)
from src.db import db

DATABASE_URL = os.getenv("DATABASE_URL", "")

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

PLACEHOLDER_NAMES = frozenset({
    "imported lab order",
    "lab test",
    "laboratory test",
    "test",
    "investigation",
    "",
})


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1: MDM Lab Catalog (preferred)
# ─────────────────────────────────────────────────────────────────────────────

def run_from_catalog(dry_run: bool = False) -> None:
    """Resolve test names by joining lab_orders.test_code → royan_lab_catalog."""
    log.info("Strategy: MDM lab catalog join")

    database_url = DATABASE_URL
    if not database_url:
        log.error(
            "DATABASE_URL not set. Set it in backend/.env or export DATABASE_URL=..."
        )
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # Count placeholders
            cur.execute("""
                SELECT COUNT(*)
                FROM public.royan_lab_orders lo
                WHERE lo.external_source = 'hope'
                  AND lower(lo.test_name) = ANY(%s)
                  AND lo.test_code IS NOT NULL
                  AND lo.test_code != ''
            """, (list(PLACEHOLDER_NAMES),))
            total = cur.fetchone()[0]
            log.info("Found %d placeholder lab orders with a test_code", total)

            if total == 0:
                log.info("Nothing to backfill via catalog.")
                return

            # Resolve via catalog
            cur.execute("""
                SELECT lo.id, lo.test_code, lc.name AS catalog_name
                FROM public.royan_lab_orders lo
                JOIN public.royan_lab_catalog lc ON lc.code = lo.test_code
                WHERE lo.external_source = 'hope'
                  AND lower(lo.test_name) = ANY(%s)
                  AND lo.test_code IS NOT NULL
                  AND lo.test_code != ''
                  AND lc.is_active = true
            """, (list(PLACEHOLDER_NAMES),))
            matches = cur.fetchall()
            log.info("Catalog resolved %d / %d orders", len(matches), total)

            if not matches:
                log.warning(
                    "No catalog matches found. Run 'python ingest.py --entity master' "
                    "first to populate royan_lab_catalog from Hope data."
                )
                return

            updated = 0
            for order_id, test_code, catalog_name in matches:
                log.info(
                    "%s id=%d  code=%s  →  '%s'",
                    "[DRY RUN]" if dry_run else "UPDATE",
                    order_id,
                    test_code,
                    catalog_name,
                )
                if not dry_run:
                    cur.execute(
                        "UPDATE public.royan_lab_orders SET test_name = %s WHERE id = %s",
                        (catalog_name, order_id),
                    )
                updated += 1

            # Also update catalog_id FK for resolved orders
            if not dry_run:
                cur.execute("""
                    UPDATE public.royan_lab_orders lo
                    SET catalog_id = lc.id
                    FROM public.royan_lab_catalog lc
                    WHERE lc.code = lo.test_code
                      AND lc.is_active = true
                      AND lo.catalog_id IS NULL
                      AND lo.test_code IS NOT NULL
                      AND lo.test_code != ''
                """)
                fk_updated = cur.rowcount
                log.info("Set catalog_id FK on %d lab orders", fk_updated)

                conn.commit()
                log.info("Committed.")
            else:
                log.info("[DRY RUN] Would update %d orders. No writes.", updated)

        log.info("Done. Updated=%d%s", updated, " [DRY RUN]" if dry_run else "")

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2: Hope Bridge API (original strategy)
# ─────────────────────────────────────────────────────────────────────────────

_TEST_NAME_FIELDS = [
    "test_name", "test", "investigation", "lab_test",
    "test_type", "description", "service_name", "item_name",
]


def _safe(val: object) -> str | None:
    s = str(val).strip() if val is not None else ""
    return s or None


def _extract_test_name(row: dict) -> str | None:
    row_lower = {k.lower(): v for k, v in row.items()}
    for field in _TEST_NAME_FIELDS:
        val = _safe(row_lower.get(field))
        if val and val.lower() not in PLACEHOLDER_NAMES:
            return val
    return None


def _fetch_hope_lab(limit: int) -> list[dict]:
    headers = {"X-Bridge-Key": HOPE_BRIDGE_KEY} if HOPE_BRIDGE_KEY else {}
    try:
        resp = requests.get(
            f"{HOPE_BRIDGE_URL.rstrip('/')}/lab/orders",
            params={"limit": limit},
            headers=headers,
            timeout=HOPE_BRIDGE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, list) else list(payload.get("data") or [])
    except Exception as exc:
        log.error("Hope Bridge fetch failed: %s", exc)
        return []


def run_from_bridge(dry_run: bool = False, batch: int = 200) -> None:
    log.info("Strategy: Hope Bridge API")

    result = (
        db.table(TABLE_LAB_ORDERS)
        .select("id, external_id, test_name")
        .eq("external_source", "hope")
        .in_("test_name", list(PLACEHOLDER_NAMES))
        .execute()
    )
    targets: list[dict] = result.data or []
    log.info("Found %d placeholder records.", len(targets))

    if not targets:
        log.info("Nothing to backfill.")
        return

    log.info("Fetching up to %d rows from Hope Bridge…", batch)
    hope_rows = _fetch_hope_lab(batch)
    log.info("Retrieved %d rows from Hope.", len(hope_rows))

    hope_index: dict[str, str] = {}
    for row in hope_rows:
        ext_id = _safe(row.get("order_id") or row.get("id"))
        if not ext_id:
            continue
        name = _extract_test_name(row)
        if name:
            hope_index[ext_id] = name

    log.info("Resolved test names for %d Hope IDs.", len(hope_index))

    updated = skipped = 0
    for rec in targets:
        ext_id = rec.get("external_id")
        new_name = hope_index.get(ext_id) if ext_id else None
        if not new_name:
            skipped += 1
            continue
        log.info(
            "%s id=%s ext=%s → '%s'",
            "[DRY RUN]" if dry_run else "UPDATE",
            rec["id"], ext_id, new_name,
        )
        if not dry_run:
            db.table(TABLE_LAB_ORDERS).update({"test_name": new_name}).eq("id", rec["id"]).execute()
        updated += 1

    log.info(
        "Done. Updated=%d Skipped=%d%s",
        updated, skipped,
        " [DRY RUN]" if dry_run else "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument(
        "--from-bridge",
        action="store_true",
        help="Use Hope Bridge API instead of MDM catalog (requires live bridge)",
    )
    parser.add_argument("--batch", type=int, default=200, help="Hope Bridge fetch limit")
    args = parser.parse_args()

    if args.from_bridge:
        run_from_bridge(dry_run=args.dry_run, batch=args.batch)
    else:
        run_from_catalog(dry_run=args.dry_run)
