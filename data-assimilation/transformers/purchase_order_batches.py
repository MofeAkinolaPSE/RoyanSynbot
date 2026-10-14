"""Extract real historical purchase-order batch/cost records from Hope's
`purchase_order_items` (staged as hope_purchase_order_items) -> additional
royan_inventory_batches rows, reusing load_purchase_batches unmodified
(same target as transformers/pharmacy_purchase_batches.py's much thinner
inventory_purchase_item_details source, only ~37 rows there vs 17,186 here).

product_id confirmed (by direct id-overlap check, not assumed) to share
the same id space as Hope's pharmacy_items -- the source
transformers/pharmacy_catalog.py already used to build royan_drug_formulary
-- 758/810 distinct product_ids (93.6%) resolve.

quantity_on_hand forced to 0 (not the real received qty), same rationale
as pharmacy_purchase_batches.py: these are historical purchase records
(2017-2025) whose stock has long since moved; treating them as still "on
hand" would double-count against the HOPE-INITIAL current-stock batch.
purchase_price is the real internal cost per unit -- the actual unit-cost
answer the pharmacy inventory work earlier in this project approximated
via dispensing-history backfill.

external_id prefixed "po_item:" (not the bare Hope id) to avoid colliding
with pharmacy_catalog.py's "HOPE-INITIAL" batches and
pharmacy_purchase_batches.py's "purchase:" prefixed batches, which share
the same (external_source, external_id) key space on royan_inventory_batches.

royan_inventory_batches also has a UNIQUE(formulary_id, lower(batch_number))
constraint, meant for live inventory (one current record per physical
batch) -- but Hope's real batch_number is reused ~13x on average per drug
across different purchase events over 8 years (confirmed: 16,647 resolvable
rows collapse to only 1,230 distinct (item_id, batch) pairs), not a real
per-shipment lot key in this context. The real batch code is kept as the
visible prefix with the Hope purchase-item id appended for uniqueness,
since these are archival cost/expiry history rows, not live-tracked stock.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _to_number(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        if not s or s.lower() == "none":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}
        product_id = safe_str(raw.get("product_id"))
        batch_number = safe_str(raw.get("batch_number"))
        ext_id = safe_str(raw.get("id"))
        qty = _to_number(raw.get("quantity_received"))
        if not product_id or not batch_number or not ext_id or not qty or qty <= 0:
            continue

        purchase_price = _to_number(raw.get("purchase_price")) or 0

        payload = {
            "_hope_item_id":     product_id,
            "batch_number":      f"{batch_number}-{ext_id}",
            "quantity_received": qty,
            "quantity_on_hand":  0,
            "unit_cost":         round(purchase_price, 2),
            "expiry_date":       safe_date(raw.get("expiry_date")),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       f"po_item:{ext_id}",
        }
        # received_at is NOT NULL DEFAULT CURRENT_DATE on the live table --
        # omit the key entirely (rather than pass an explicit None) so the
        # DB default applies for the ~2% of rows missing a real date.
        received_at = safe_date(raw.get("received_date"))
        if received_at:
            payload["received_at"] = received_at
        out.append(payload)
    return out
