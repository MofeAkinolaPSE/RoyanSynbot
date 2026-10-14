"""PHASE D - the final Hope dump pass (2026-08-28).

WHY THIS EXISTS
---------------
Client staff meetings asked us to find, in the data: insurance numbers, room
tariffs, lab test costs, HMO codes, ambulance billing, departments, and "all the
services the hospital provides along with the service cost".

The survey found almost all of it was ALREADY STAGED and simply never loaded --
new_insurances (162,991 rows), tariff_amounts (56,732), departments (513),
rooms, laboratories. Only ONE table has a proven gap:

    tariff_amounts references 1,578 distinct tariff_list_id values.
    raw_hope_tariff_lists holds 434 rows (ids 261..2167).
    => 17,401 of 24,273 priced rows (72%) cannot be resolved to a service.

Ids 0-260 are missing as a contiguous block and NO row points at id 0, so these
are real references to real services we never extracted. tariff_lists is the
keystone: rooms, laboratories, radiologies and surgeries all carry a
tariff_list_id, so recovering it prices everything at once.

SCOPE
-----
A dump pass costs the same regardless of table count, and the client asked for
this to be done once. So the target set is deliberately generous: it re-pulls
tables already staged (we found one silent truncation; there may be others) and
includes name guesses for groups whose real Hope names we do not know.

A wrong guess costs nothing -- parse_dump returns no rows for a name that does
not exist. A MISSING table costs a whole second pass.

Usage: python scripts/extract_phase_d_pricing_identity.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.mysql_dump import parse_dump
from staging.sqlite_store import StagingStore

# Three Phase A loads failed silently because no driver configured logging.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

DUMP_PATH = str(
    Path(__file__).resolve().parent.parent / "Docs" / "NEw Dump" / "db_drmnigeria-20260125.sql.gz"
)

INVENTORY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "backend" / "docs" / "Post-deployment-mods" / "HOPE_TABLE_INVENTORY.md"
)

# --- The keystone. Everything else in this pass is opportunistic. ----------
PRICING = {
    "tariff_lists", "tariff_amounts", "tariff_standards",
    "tariff_list_items", "tariff_details", "tariff_categories", "tariff_types",
    "service_categories", "service_sub_categories", "service_charges",
    "product_rates", "corporate_lab_rates",
    "price_lists", "prices", "charges", "rate_masters", "service_masters",
}

# --- Payer identity: the insurance numbers asked for in BOTH meetings ------
PAYER = {
    "new_insurances", "insurance_companies", "insurance_types",
    "insurance_authorizations", "patient_insurances", "insurances",
    "corporates", "corporate_patient_details", "corporate_super_bills",
    "corporate_super_bill_lists", "corporate_locations", "corporate_sublocations",
}

# --- Rooms, wards, departments, consulting rooms --------------------------
PLACES = {
    "rooms", "wards", "beds", "departments", "chambers", "doctor_chambers",
    "locations", "room_types", "bed_types", "ward_categories",
}

# --- Service masters. Each carries a tariff_list_id into the pricing grid --
SERVICE_MASTERS = {
    "laboratories", "laboratory_categories", "radiologies", "surgeries",
    "surgery_categories", "surgery_subcategories", "surgery_sub_categories",
    "pharmacy_items", "pharmacy_item_rates", "procedure_masters",
}

# --- Staff / attendance: the client's clock-out complaint -----------------
# Real Hope names unknown; the inventory this run produces will resolve them.
STAFF = {
    "employees", "staffs", "staff", "users", "doctors", "consultants",
    "attendances", "attendance", "user_attendances", "employee_attendances",
    "staff_attendances", "timesheets", "time_sheets", "duty_rosters", "shifts",
}

# --- Ambulance: client asked whether any billing exists for it ------------
AMBULANCE = {
    "ambulances", "ambulance_services", "ambulance_bookings",
    "ambulance_charges", "ambulance_trips",
}

TARGET_TABLES = PRICING | PAYER | PLACES | SERVICE_MASTERS | STAFF | AMBULANCE

ENTITY_MAP = {t: "hope_" + t for t in TARGET_TABLES}


def _fmt(n):
    return "{:,}".format(n)


def write_inventory(all_tables, staged_counts):
    """Record every table the dump defines.

    parse_dump seeds a key for every CREATE TABLE it sees, so this is the full
    Hope schema -- the artefact that lets us prove no relevant table was
    overlooked, rather than hoping.

    Row counts are real for targeted tables ONLY. Untargeted tables are listed
    by name: this pass did not collect their rows, so a missing count here means
    "not collected", never "empty". Saying that plainly matters, because an
    earlier phase drew exactly that wrong conclusion from a similar artefact.
    """
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    targeted = sorted(t for t in all_tables if t in TARGET_TABLES)
    other = sorted(t for t in all_tables if t not in TARGET_TABLES)

    lines = [
        "# Hope dump - full table inventory",
        "",
        "Generated by `data-assimilation/scripts/extract_phase_d_pricing_identity.py`.",
        "Source: `Docs/NEw Dump/db_drmnigeria-20260125.sql.gz`",
        "",
        "Row counts are REAL for targeted tables. Untargeted tables are listed by",
        "name only - this pass did not collect their rows, so the absence of a",
        'count here means "not collected", NOT "empty".',
        "",
        "Tables defined in dump: **" + str(len(all_tables)) + "**",
        "",
        "## Targeted this pass (" + str(len(targeted)) + ")",
        "",
        "| table | rows staged |",
        "|---|---|",
    ]
    for t in targeted:
        lines.append("| `" + t + "` | " + _fmt(staged_counts.get(t, 0)) + " |")

    lines += [
        "",
        "## Not targeted (" + str(len(other)) + ") - names only",
        "",
        ", ".join("`" + t + "`" for t in other),
        "",
    ]

    INVENTORY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("  inventory -> " + str(INVENTORY_PATH))


def main():
    print("Streaming " + DUMP_PATH)
    print("Targeting " + str(len(TARGET_TABLES)) + " table names (wrong guesses are free)")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print("Parse complete in " + str(int(time.time() - t0)) + "s")
    print("Tables defined in dump: " + str(len(data)))
    print("")

    store = StagingStore()
    run_id = "phase_d_" + str(int(time.time()))

    staged = {}
    absent = []
    empty = []
    for hope_table, entity in sorted(ENTITY_MAP.items()):
        if hope_table not in data:
            absent.append(hope_table)          # guessed name; no such table
            continue
        rows = data.get(hope_table) or []
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        staged[hope_table] = count
        if count:
            print("  " + hope_table.ljust(34) + " -> " + _fmt(count).rjust(9) + " rows")
        else:
            empty.append(hope_table)

    print("")
    print("Exists but empty (" + str(len(empty)) + "): " + (", ".join(empty) or "-"))
    print("")
    print("Guessed names with no such table (" + str(len(absent)) + "): " + (", ".join(absent) or "-"))
    print("")

    # The whole point of the pass.
    tl = staged.get("tariff_lists", 0)
    bar = "=" * 62
    print(bar)
    print("KEYSTONE CHECK - tariff_lists")
    print("  previously staged : 434 rows (ids 261..2167)")
    print("  this pass         : " + _fmt(tl) + " rows")
    if tl > 434:
        print("  => RECOVERED. Re-run the resolution query; up to 17,401 priced")
        print("     rows should now resolve to a real service.")
    elif tl == 434:
        print("  => UNCHANGED. tariff_lists genuinely IS 434 rows, so the 17,401")
        print("     unresolvable rows reference services Hope deleted. That is a")
        print("     finding to report, not a failure to retry.")
    else:
        print("  => FEWER than before. Do NOT overwrite earlier conclusions;")
        print("     investigate the parse before trusting this run.")
    print(bar)

    write_inventory(set(data.keys()), staged)
    print("Done.")


if __name__ == "__main__":
    main()
