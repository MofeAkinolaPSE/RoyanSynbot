"""RoyanHealth Data Assimilation Layer — DRM Hope MySQL → RoyanHealth

DEPRECATED: Use pipeline.py for all new runs (v2 orchestrator with Medallion
Architecture, Pydantic contracts, DLQ, incremental mode, and parallel processing).
This file is kept for backward compatibility and --step discover.

Usage examples:
  # Step 1: See what tables exist in the dump (nothing is written)
  python ingest.py --source dump --file hope_export.sql --step discover

  # Step 2: Load all entities
  python ingest.py --source dump --file hope_export.sql --entity all

  # Load one entity at a time
  python ingest.py --source dump --file hope_export.sql --entity patients
  python ingest.py --source dump --file hope_export.sql --entity appointments

  # Dry run: see what would be loaded without writing anything
  python ingest.py --source dump --file hope_export.sql --entity patients --dry-run

  # CSV fallback (one CSV per table, filenames = table names)
  python ingest.py --source csv --folder ./hope_csvs --entity all
"""
from __future__ import annotations

import argparse
import sys
import traceback
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Entity processing order (patients must be first — others depend on it).
# Derived entities (lab_results, dispensing, payments, insurance_claims) run
# AFTER their parent entities so the FK targets already exist in PostgreSQL.
# ---------------------------------------------------------------------------
ENTITY_ORDER = [
    "patients", "appointments", "admissions",
    "lab", "pharmacy", "billing",
    "lab_results", "dispensing", "payments", "insurance_claims",
]

# Maps each derived entity to the raw staging table it reads from.
# Derived entities share staging data with their parent entity.
_STAGING_SOURCE = {
    "patients":         "patients",
    "appointments":     "appointments",
    "admissions":       "admissions",
    "lab":              "lab",
    "pharmacy":         "pharmacy",
    "billing":          "billing",
    "lab_results":      "lab",       # same raw staging as lab orders
    "dispensing":       "pharmacy",  # same raw staging as prescriptions
    "payments":         "billing",   # same raw staging as billing
    "insurance_claims": "billing",   # same raw staging as billing
}

# Primary entities that require their own staging slot (all others re-use a parent's)
_PRIMARY_ENTITIES = {"patients", "appointments", "admissions", "lab", "pharmacy", "billing"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DRM Hope → RoyanHealth data ingestion tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=["dump", "csv"], required=True,
                        help="dump = MySQL .sql file;  csv = folder of CSV files")
    parser.add_argument("--file", help="Path to .sql dump file (--source dump)")
    parser.add_argument("--folder", help="Path to CSV folder (--source csv)")
    parser.add_argument(
        "--entity",
        default="all",
        help="Entity to process: all | patients | appointments | admissions | lab | pharmacy | billing",
    )
    parser.add_argument(
        "--step",
        default="all",
        choices=["discover", "extract", "stage", "transform", "load", "all"],
        help="Pipeline step to run (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Transform and show what would be loaded — no DB writes")
    parser.add_argument("--from-staging", action="store_true",
                        help="Skip extraction/staging — load directly from existing SQLite staging DB")

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # STEP: discover — just print schema, exit
    # -----------------------------------------------------------------------
    if args.step == "discover":
        if args.source != "dump" or not args.file:
            print("ERROR: --step discover requires --source dump --file <path>")
            sys.exit(1)
        from extractors.mysql_dump import discover
        discover(args.file)
        return

    # -----------------------------------------------------------------------
    # Validate inputs
    # -----------------------------------------------------------------------
    if args.source == "dump" and not args.file and not getattr(args, "from_staging", False):
        print("ERROR: --source dump requires --file <path_to_.sql>")
        sys.exit(1)
    if args.source == "csv" and not args.folder:
        print("ERROR: --source csv requires --folder <path_to_csv_folder>")
        sys.exit(1)

    entities = ENTITY_ORDER if args.entity == "all" else [args.entity.lower()]
    for e in entities:
        if e not in ENTITY_ORDER:
            print(f"ERROR: unknown entity '{e}'. Choose from: {', '.join(ENTITY_ORDER)} or all")
            sys.exit(1)

    # When only primary entities are requested, filter out derived ones automatically
    if args.entity != "all":
        pass  # single-entity run; already validated above

    # -----------------------------------------------------------------------
    # Load DATABASE_URL from .env
    # -----------------------------------------------------------------------
    if not args.dry_run:
        try:
            import config  # noqa: F401  triggers EnvironmentError if DATABASE_URL missing
        except EnvironmentError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)

    # -----------------------------------------------------------------------
    # EXTRACTION — parse dump or CSV folder
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("RoyanHealth Data Assimilation Layer")
    print(f"Source : {args.source.upper()} — {args.file or args.folder}")
    print(f"Entities: {', '.join(entities)}")
    print(f"Dry run : {'YES — no DB writes' if args.dry_run else 'NO — will write to DB'}")
    print(f"{'='*60}\n")

    from staging.sqlite_store import StagingStore
    from transformers.field_maps import TABLE_HINTS

    staged: Dict[str, List[dict]] = {}

    if getattr(args, "from_staging", False):
        # ------------------------------------------------------------------
        # FAST PATH — per-entity read→transform→load to keep RAM usage low.
        # Reading all 1.5M staged rows at once causes OOM; process one entity
        # at a time so only ~300K rows are in memory at any point.
        # ------------------------------------------------------------------
        print("[1/4] Skipping extraction — --from-staging flag set.\n")

        import transformers.patients as _tp
        import transformers.appointments as _ta
        import transformers.admissions as _tadm
        import transformers.lab as _tlab
        import transformers.pharmacy as _tph
        import transformers.billing as _tb
        import transformers.lab_results as _tlr
        import transformers.dispensing as _tdisp
        import transformers.payments as _tpay
        import transformers.insurance_claims as _tic
        from loaders.db_loader import (
            get_conn, load_patients, load_appointments, load_admissions,
            load_lab, load_pharmacy, load_billing,
            load_lab_results, load_dispensing, load_payments, load_insurance_claims,
            log_run,
        )

        _fs_conn = None
        if not args.dry_run:
            from config import DATABASE_URL
            try:
                _fs_conn = get_conn(DATABASE_URL)
                print("  Connected to PostgreSQL.\n")
            except Exception as exc:
                print(f"  ERROR: Could not connect: {exc}")
                sys.exit(1)

        _fs_store = StagingStore()
        _fs_summary: Dict[str, str] = {}

        _TRANSFORM = {
            "patients":         lambda r: _tp.transform(r),
            "appointments":     lambda r: _ta.transform(r),
            "admissions":       lambda r: _tadm.transform(r),
            "lab":              lambda r: _tlab.transform(r),
            "pharmacy":         lambda r: _tph.transform(r),
            "billing":          lambda r: _tb.transform(r),
            "lab_results":      lambda r: _tlr.transform(r),
            "dispensing":       lambda r: _tdisp.transform(r),
            "payments":         lambda r: _tpay.transform(r),
            "insurance_claims": lambda r: _tic.transform(r),
        }

        # ------------------------------------------------------------------
        # Build canonical patient PID map.
        # Hope stores multiple rows per patient (one per registration event),
        # each with a different `patients.id` (DB pk) but the same MRN.
        # We derive the map FROM the patients transformer output so the canonical
        # pk chosen here is IDENTICAL to the one loaded into royan_patients.
        # ------------------------------------------------------------------
        _pid_canonical: Dict[str, str] = {}
        _patients_precomputed = None
        if "patients" in entities:
            _pid_raw = _fs_store.read_latest_run("patients")
            _patients_precomputed = _tp.transform(_pid_raw)
            _mrn_to_canonical_pk: Dict[str, str] = {
                p["mrn"]: p["external_id"] for p in _patients_precomputed
            }
            for _pr in _pid_raw:
                _pk  = str(_pr.get("id") or _pr.get("patientid") or "")
                _mrn = str(_pr.get("patient_id") or "")   # Hope: patient_id col = human MRN
                if _pk and _mrn and _mrn in _mrn_to_canonical_pk:
                    _pid_canonical[_pk] = _mrn_to_canonical_pk[_mrn]
            del _pid_raw, _mrn_to_canonical_pk
            print(f"  [pid remap] {len(_pid_canonical):,} entries -> {len(set(_pid_canonical.values())):,} canonical IDs.\n")

        for _entity in entities:
            # Derived entities re-read from their parent's staging table
            _staging_entity = _STAGING_SOURCE.get(_entity, _entity)
            print(f"  [{_entity}] reading {_fs_store.count(_staging_entity):,} rows from staging ({_staging_entity})...")
            if _entity == "patients" and _patients_precomputed is not None:
                _data = _patients_precomputed
                _patients_precomputed = None
            else:
                _raw = _fs_store.read_latest_run(_staging_entity)
                if _pid_canonical:
                    _raw = _sub_patient_ids(_raw, _pid_canonical)
                _data = _TRANSFORM[_entity](_raw)
                del _raw  # free extraction memory immediately

            if _entity == "appointments":
                _slots, _appts = _data if isinstance(_data, tuple) else ([], [])
                print(f"  [{_entity}] {len(_appts):,} appointments ready — loading...")
            else:
                print(f"  [{_entity}] {len(_data):,} payloads ready — loading...")

            _seen = _upserted = 0
            _err = None
            try:
                if _entity == "patients":
                    _seen = len(_data)
                    _, _upserted = load_patients(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "appointments":
                    _seen = len(_appts)
                    _, _upserted = load_appointments(_fs_conn, _slots, _appts, dry_run=args.dry_run)
                elif _entity == "admissions":
                    _seen = len(_data)
                    _, _upserted = load_admissions(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "lab":
                    _seen = len(_data)
                    _, _upserted = load_lab(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "pharmacy":
                    _seen = len(_data)
                    _, _upserted = load_pharmacy(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "billing":
                    _seen = len(_data)
                    _, _upserted = load_billing(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "lab_results":
                    _seen = len(_data)
                    _, _upserted = load_lab_results(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "dispensing":
                    _seen = len(_data)
                    _, _upserted = load_dispensing(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "payments":
                    _seen = len(_data)
                    _, _upserted = load_payments(_fs_conn, _data, dry_run=args.dry_run)
                elif _entity == "insurance_claims":
                    _seen = len(_data)
                    _, _upserted = load_insurance_claims(_fs_conn, _data, dry_run=args.dry_run)

                if _fs_conn and not args.dry_run:
                    log_run(_fs_conn, _entity, _seen, _upserted)

                _lbl = "would upsert" if args.dry_run else "upserted"
                _fs_summary[_entity] = f"{_seen} seen, {_upserted} {_lbl}"
                print(f"  {_entity}: {_fs_summary[_entity]}")

            except Exception as exc:
                _err = str(exc)
                _fs_summary[_entity] = f"FAILED — {_err}"
                print(f"  {_entity}: ERROR — {_err}")
                if _fs_conn:
                    # Step 1: always reset the aborted transaction first.
                    try:
                        _fs_conn.rollback()
                    except Exception:
                        pass
                    # Step 2: attempt to log the failure (log_run handles its own rollback).
                    try:
                        log_run(_fs_conn, _entity, _seen, 0, error=_err)
                    except Exception:
                        pass
                    # Step 3: guarantee a clean connection for the next entity.
                    try:
                        _fs_conn.rollback()
                    except Exception:
                        pass
                traceback.print_exc()

            del _data  # free transform memory before next entity

        if _fs_conn:
            _fs_conn.close()

        print(f"\n{'='*60}")
        print("INGESTION COMPLETE")
        print(f"{'='*60}")
        for _entity, _result in _fs_summary.items():
            print(f"  {_entity:15s} {_result}")
        print()
        return  # skip the normal three-loop pipeline below
    else:
        # ------------------------------------------------------------------
        # NORMAL PATH — parse source + write to SQLite
        # ------------------------------------------------------------------
        print("[1/4] Extracting raw data from source...")
        raw_data: Dict[str, List[dict]] = {}

        if args.source == "dump":
            from extractors.mysql_dump import parse_dump

            if args.entity == "all":
                target_tables = {t for hints in TABLE_HINTS.values() for t in hints}
            else:
                target_tables = set(TABLE_HINTS.get(args.entity.lower(), [args.entity.lower()]))

            raw_data = parse_dump(args.file, target_tables=target_tables)
            print(f"  Parsed {len(raw_data)} tables from dump.\n")
        else:
            from extractors.csv_flat import extract_csv_folder
            raw_data = extract_csv_folder(args.folder)
            print(f"  Read {len(raw_data)} CSV files.\n")

        print("[2/4] Staging raw data to SQLite...")
        store = StagingStore()

        for entity in entities:
            raw_rows = _resolve_entity_rows(raw_data, entity, TABLE_HINTS)
            if raw_rows is None:
                print(f"  WARNING: No table found for entity '{entity}'. Tried: {TABLE_HINTS.get(entity)}")
                staged[entity] = []
                continue
            store.clear(entity)
            count = store.write(entity, raw_rows)
            store.record_run(entity, args.source, count)
            staged[entity] = raw_rows
            print(f"  {entity}: {count} rows staged.")

    # -----------------------------------------------------------------------
    # TRANSFORMATION
    # -----------------------------------------------------------------------
    print("\n[3/4] Transforming staged data...")
    import transformers.patients as t_patients
    import transformers.appointments as t_appointments
    import transformers.admissions as t_admissions
    import transformers.lab as t_lab
    import transformers.pharmacy as t_pharmacy
    import transformers.billing as t_billing
    import transformers.lab_results as t_lab_results
    import transformers.dispensing as t_dispensing
    import transformers.payments as t_payments
    import transformers.insurance_claims as t_insurance_claims

    transformed: Dict[str, Any] = {}

    for entity in entities:
        # Derived entities use already-staged data from their parent
        staging_key = _STAGING_SOURCE.get(entity, entity)
        raw = staged.get(staging_key, [])
        if not raw:
            print(f"  {entity}: no rows to transform.")
            transformed[entity] = [] if entity != "appointments" else ([], [])
            continue

        if entity == "patients":
            result = t_patients.transform(raw)
            print(f"  patients: {len(result)} payloads ready.")
        elif entity == "appointments":
            slots, appts = t_appointments.transform(raw)
            result = (slots, appts)
            print(f"  appointments: {len(slots)} slots + {len(appts)} appointments ready.")
        elif entity == "admissions":
            result = t_admissions.transform(raw)
            print(f"  admissions: {len(result)} encounter payloads ready.")
        elif entity == "lab":
            result = t_lab.transform(raw)
            print(f"  lab: {len(result)} order payloads ready.")
        elif entity == "pharmacy":
            result = t_pharmacy.transform(raw)
            print(f"  pharmacy: {len(result)} prescription payloads ready.")
        elif entity == "billing":
            result = t_billing.transform(raw)
            print(f"  billing: {len(result)} bill payloads ready.")
        elif entity == "lab_results":
            result = t_lab_results.transform(raw)
            print(f"  lab_results: {len(result)} result payloads ready.")
        elif entity == "dispensing":
            result = t_dispensing.transform(raw)
            print(f"  dispensing: {len(result)} dispensing payloads ready.")
        elif entity == "payments":
            result = t_payments.transform(raw)
            print(f"  payments: {len(result)} payment payloads ready.")
        elif entity == "insurance_claims":
            result = t_insurance_claims.transform(raw)
            print(f"  insurance_claims: {len(result)} claim payloads ready.")
        else:
            result = []

        transformed[entity] = result

    # -----------------------------------------------------------------------
    # LOADING — write to PostgreSQL
    # -----------------------------------------------------------------------
    print("\n[4/4] Loading into RoyanHealth database...")

    if args.dry_run:
        print("  DRY RUN — no database writes.\n")

    from loaders.db_loader import (
        get_conn,
        load_admissions,
        load_appointments,
        load_billing,
        load_lab,
        load_patients,
        load_pharmacy,
        load_lab_results,
        load_dispensing,
        load_payments,
        load_insurance_claims,
        log_run,
    )

    conn = None
    if not args.dry_run:
        from config import DATABASE_URL
        try:
            conn = get_conn(DATABASE_URL)
            print(f"  Connected to PostgreSQL.\n")
        except Exception as exc:
            print(f"  ERROR: Could not connect to database: {exc}")
            print("  Check DATABASE_URL in your .env file.")
            sys.exit(1)

    summary: Dict[str, str] = {}

    for entity in entities:
        data = transformed.get(entity)
        seen = 0
        upserted = 0
        error = None

        try:
            if entity == "patients":
                rows = data or []
                seen = len(rows)
                _, upserted = load_patients(conn, rows, dry_run=args.dry_run)
            elif entity == "appointments":
                slots, appts = data if isinstance(data, tuple) else ([], [])
                seen = len(appts)
                _, upserted = load_appointments(conn, slots, appts, dry_run=args.dry_run)
            elif entity == "admissions":
                rows = data or []
                seen = len(rows)
                _, upserted = load_admissions(conn, rows, dry_run=args.dry_run)
            elif entity == "lab":
                rows = data or []
                seen = len(rows)
                _, upserted = load_lab(conn, rows, dry_run=args.dry_run)
            elif entity == "pharmacy":
                rows = data or []
                seen = len(rows)
                _, upserted = load_pharmacy(conn, rows, dry_run=args.dry_run)
            elif entity == "billing":
                rows = data or []
                seen = len(rows)
                _, upserted = load_billing(conn, rows, dry_run=args.dry_run)
            elif entity == "lab_results":
                rows = data or []
                seen = len(rows)
                _, upserted = load_lab_results(conn, rows, dry_run=args.dry_run)
            elif entity == "dispensing":
                rows = data or []
                seen = len(rows)
                _, upserted = load_dispensing(conn, rows, dry_run=args.dry_run)
            elif entity == "payments":
                rows = data or []
                seen = len(rows)
                _, upserted = load_payments(conn, rows, dry_run=args.dry_run)
            elif entity == "insurance_claims":
                rows = data or []
                seen = len(rows)
                _, upserted = load_insurance_claims(conn, rows, dry_run=args.dry_run)

            if conn and not args.dry_run:
                log_run(conn, entity, seen, upserted)

            label = "would upsert" if args.dry_run else "upserted"
            summary[entity] = f"{seen} seen, {upserted} {label}"
            print(f"  {entity}: {summary[entity]}")

        except Exception as exc:
            error = str(exc)
            summary[entity] = f"FAILED — {error}"
            print(f"  {entity}: ERROR — {error}")
            if conn and not args.dry_run:
                try:
                    conn.rollback()
                    log_run(conn, entity, seen, 0, error=error)
                except Exception:
                    pass
            traceback.print_exc()

    if conn:
        conn.close()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("INGESTION COMPLETE")
    print(f"{'='*60}")
    for entity, result in summary.items():
        print(f"  {entity:15s} {result}")
    print()


# ---------------------------------------------------------------------------
# Helper: resolve which raw table to use for each entity
# ---------------------------------------------------------------------------

def _resolve_entity_rows(
    raw_data: Dict[str, List[dict]],
    entity: str,
    table_hints: Dict[str, List[str]],
) -> Optional[List[dict]]:
    hints = table_hints.get(entity, [entity])
    for hint in hints:
        if hint in raw_data and raw_data[hint]:
            return raw_data[hint]
    # Last resort: exact match on entity name
    if entity in raw_data:
        return raw_data[entity]
    return None


def _sub_patient_ids(rows: List[dict], pid_map: Dict[str, str]) -> List[dict]:
    """Remap historical Hope patient_id FKs to their canonical (latest-per-MRN) equivalent.

    Hope keeps multiple patient rows per MRN (one per registration event). We load
    only the latest per MRN into royan_patients. This helper ensures that appointment,
    lab, pharmacy, and billing rows referencing any historical patient_id FK get
    redirected to the canonical one so the royan_patients lookup succeeds.
    """
    if not pid_map:
        return rows
    out = []
    for row in rows:
        for col in ("patient_id", "patientid"):
            if col in row:
                old_val = str(row.get(col) or "")
                canonical = pid_map.get(old_val)
                if canonical and canonical != old_val:
                    row = {**row, col: canonical}
                break
        out.append(row)
    return out


if __name__ == "__main__":
    main()
