"""Extract Royan's real drug/item catalog from Hope's `pharmacy_items` table
(staged as `hope_pharmacy_catalog`) -> royan_drug_formulary + an initial
royan_inventory_batches row per drug carrying its current stock snapshot.

Hope's `genericdrugname` column is unpopulated (literal "0" on every row in
this dump) so `name` (the actual product name, e.g. "ACETYSALICYLIC ACID
300MG TAB") is used for both generic_name and brand_name. `item_code` is
used as royan_drug_formulary.code (UNIQUE) — duplicates/blanks are dropped,
last-write-wins by id.

drug_class/form default to 'other': Hope's catalog mixes real drugs with
non-drug items (e.g. "ACCU CHECK MACHINE", a glucose meter) and rarely
populates a real dosage form, so guessing a specific pharmaceutical class
or form (tablet/capsule/injection/...) would be asserting something the
source data doesn't actually support.

The batch is a single synthetic "initial stock" batch per drug (Hope has no
real batch/lot tracking in this table) carrying quantity_on_hand=stock,
quantity_received=opening_stock, so the Inventory workspace has a real,
non-zero starting quantity instead of an empty shelf.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow

INITIAL_BATCH_NUMBER = "HOPE-INITIAL"

# Hope's pharmacy_items has no real category/type field (item_type is a
# constant "1" on every one of the 956 rows, theraputiccategory is empty on
# all of them) -- name-pattern matching is the only signal available.
# Calibrated against this dump's actual names, not a generic drug list:
# "vaccine" is the only vaccine-naming convention seen (e.g. "ANTIRABIES
# VACCINE" -- broader immunization-schedule name matching (BCG/OPV/etc) was
# tried and found zero additional real hits, so it's intentionally omitted
# to avoid false positives). The consumable list below is every keyword
# confirmed present verbatim in real item names (cannulas, gloves, gauze,
# syringes, needles, plasters, etc.) -- not a generic catalog list either.
_VACCINE_RE = re.compile(r"\bvaccine\b", re.IGNORECASE)
_CONSUMABLE_RE = re.compile(
    r"cannula|glove|gauze|bandage|needle|syringe|plaster|\bmask\b|cotton|swab|"
    r"catheter|dressing|\bsuture|surgical blade|speculum|tourniquet|\bdrape|"
    r"foley|giving set|\biv set|electrode|test strip|lancet|specimen|"
    r"sample bottle|urine bag|ng tube|feeding tube",
    re.IGNORECASE,
)


def _classify_category(name: str) -> str:
    if _VACCINE_RE.search(name):
        return "vaccine"
    if _CONSUMABLE_RE.search(name):
        return "consumable"
    return "drug"


def _to_number(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        if not s or s.lower() == "none":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def transform_formulary(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_codes: set = set()
    # Latest-by-id wins on duplicate codes — iterate in id order so later
    # rows overwrite earlier ones in the seen_codes membership check below.
    for row in sorted(raw_rows, key=lambda r: _to_number(r.get("id")) or 0):
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        code = safe_str(row.get("item_code"))
        ext_id = safe_str(row.get("id"))
        if not name or not code or not ext_id:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)

        unit_cost = _to_number(row.get("unit_cost")) or 0.0
        reorder_level = _to_number(row.get("reorder_level"))

        out.append({
            "code":                  code,
            "generic_name":          name,
            "brand_name":            name,
            "drug_class":            "other",
            "form":                  "other",
            "category":              _classify_category(name),
            "unit":                  safe_str(row.get("doseform")) or "unit",
            "unit_cost":             round(unit_cost, 2),
            "reorder_level":         reorder_level,
            "is_active":             True,
            "external_source":       EXTERNAL_SOURCE,
            "external_id":           ext_id,
            # carried through only for the batch-building step, stripped
            # before insert by the loader (not a real royan_drug_formulary column)
            "_stock":                _to_number(row.get("stock")),
            "_opening_stock":        _to_number(row.get("opening_stock")),
            "_expiry_date":          safe_date(row.get("expiry_date")),
            "_received_at":          safe_date(row.get("create_time")) or utcnow(),
            "_supplier_id":          safe_str(row.get("supplier_id")),
        })
    return out
