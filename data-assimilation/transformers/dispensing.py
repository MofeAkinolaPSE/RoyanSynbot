"""Extract real per-line dispensing events from Hope's
`pharmacy_sales_bill_details` table (staged as `hope_dispensing_lines`)
-> royan_dispensing.

This REPLACES the earlier design that tried to derive dispensing from
`raw_pharmacy` (pharmacy_sales_bills) rows -- that table is the SALE
HEADER (bill_code, total, payment_mode) with no drug/quantity/batch
fields at all, so that path always emitted zero rows.
`pharmacy_sales_bill_details` is the real per-item line table, linked
back to the header via `pharmacy_sales_bill_id` -- which is exactly the
Hope id already loaded as royan_prescriptions.external_id (see
transformers/pharmacy.py). So each detail line maps to the prescription
built from its parent header.

item_id resolves to a real drug name via the `pharmacy_items` catalog
(staged as `hope_pharmacy_catalog`, passed in as `item_catalog`) -- when
unavailable, falls back to the placeholder used for the parent
prescription rather than inventing a different one, keeping partial data
honestly labelled instead of a discrepant guess.

Each row gets its own external_id (the Hope pharmacy_sales_bill_details.id),
so the loader can do a normal ON CONFLICT upsert instead of the old
one-line-per-prescription restriction -- a sale legitimately has 1..N
dispensed items (~2.4 lines/bill on average in this dataset).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(str(value).replace(",", "")) if value is not None else default
        return v if v >= 0 else default
    except (ValueError, TypeError):
        return default


def transform(
    raw_rows: List[Dict[str, Any]],
    item_catalog: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    item_catalog = item_catalog or {}
    out = []

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id"))
        rx_ext_id = safe_str(raw.get("pharmacy_sales_bill_id"))
        if not ext_id or not rx_ext_id:
            continue

        qty = _to_float(raw.get("qty"), default=0.0)
        if qty <= 0:
            continue  # CHECK constraint requires quantity_dispensed > 0

        item_id = safe_str(raw.get("item_id"))
        drug_name = (item_catalog.get(item_id) if item_id else None) or "Imported prescription"

        unit_cost = _to_float(raw.get("sale_price")) or _to_float(raw.get("mrp"))

        out.append({
            "_hope_rx_ext_id":    rx_ext_id,
            # Same id space as pharmacy_items.id -- the source pharmacy_catalog.py
            # used for royan_drug_formulary.external_id -- lets the loader link
            # this real transaction price back to its formulary row.
            "_hope_item_id":      item_id,
            "drug_name":          drug_name,
            "batch_number":       safe_str(raw.get("batch_number")),
            "expiry_date":        safe_date(raw.get("expiry_date")),
            "quantity_dispensed": qty,
            "unit":               "unit",
            "dispensed_by":       "hope_ingest",
            "unit_cost":          unit_cost,
            "counselling_given":  False,
            "notes":              None,
            "external_source":    EXTERNAL_SOURCE,
            "external_id":        ext_id,
            "external_updated_at": utcnow(),
        })

    return out
