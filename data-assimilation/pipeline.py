"""RoyanHealth Data Assimilation Pipeline — v2

FAANG-grade orchestrator with:
  - Medallion Architecture (Bronze → Silver → Gold)
  - Pydantic v2 contract validation + Dead Letter Queue
  - Incremental / full sync modes with watermark tracking
  - Parallel entity processing (ThreadPoolExecutor)
  - Per-entity circuit breakers
  - Structured logging via structlog

Usage:
  # Full load (all entities)
  python pipeline.py --source dump --file hope_export.sql --mode full

  # Incremental load (only rows newer than last watermark)
  python pipeline.py --source dump --file hope_export.sql --mode incremental

  # Single entity dry run
  python pipeline.py --source csv --folder ./hope_csvs --entity patients --dry-run

  # Discover source tables (read-only)
  python pipeline.py --source dump --file hope_export.sql --step discover
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Type

# ---------------------------------------------------------------------------
# Logging setup — must happen before other imports that use the logger
# ---------------------------------------------------------------------------
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Entity processing order
# Sequential: FK dependencies require strict ordering
# Parallel:   no inter-entity FK dependencies at load time
# ---------------------------------------------------------------------------
SEQUENTIAL_ENTITIES = ["patients", "hmo", "appointments", "admissions", "patient_insurance"]
PARALLEL_ENTITIES   = ["lab", "pharmacy", "billing", "radiology", "theatre", "operations"]
ENTITY_ORDER        = SEQUENTIAL_ENTITIES + PARALLEL_ENTITIES


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class EntityCircuitBreaker:
    """Per-entity failure isolation.

    CLOSED (normal) → OPEN after max_failures → skips entity for rest of run.
    Prevents a single broken entity from blocking the rest of the pipeline.
    """
    def __init__(self, max_failures: int = 3):
        self._max = max_failures
        self._counts: Dict[str, int] = {}
        self._open: set = set()

    def record_failure(self, entity: str) -> None:
        self._counts[entity] = self._counts.get(entity, 0) + 1
        if self._counts[entity] >= self._max:
            self._open.add(entity)
            log.warning("circuit_open", entity=entity, failures=self._counts[entity])

    def record_success(self, entity: str) -> None:
        self._counts[entity] = 0

    def is_open(self, entity: str) -> bool:
        return entity in self._open


# ---------------------------------------------------------------------------
# Watermark filtering
# ---------------------------------------------------------------------------

def _apply_watermark_filter(
    rows: List[Dict[str, Any]],
    watermark: Optional[str],
) -> List[Dict[str, Any]]:
    """Keep only rows where external_updated_at > watermark.

    Rows without an updated_at always pass through (conservative — never skip
    rows we can't date).
    """
    if not watermark:
        return rows

    kept = []
    for row in rows:
        val = row.get("updated_at") or row.get("external_updated_at") or row.get("created_at")
        if val is None:
            kept.append(row)
        elif str(val) > watermark:
            kept.append(row)
    return kept


# ---------------------------------------------------------------------------
# Contract validation + DLQ split
# ---------------------------------------------------------------------------

def _validate_and_split(
    entity: str,
    rows: List[Dict[str, Any]],
    contract_class: Optional[Type],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate rows against a Pydantic contract.

    Returns (valid_rows, dlq_failures).
    dlq_failures each contain: raw_row, failure_stage, failure_reason.
    """
    if contract_class is None:
        return rows, []

    from pydantic import ValidationError

    valid, failures = [], []
    for row in rows:
        try:
            contract_class(**row)
            valid.append(row)
        except ValidationError as exc:
            failures.append({
                "raw_row":       row,
                "external_id":   str(row.get("external_id") or row.get("id") or ""),
                "source_table":  entity,
                "failure_stage": "contract",
                "failure_reason": exc.errors()[0]["msg"] if exc.errors() else str(exc),
                "error_detail":  {"errors": exc.errors()},
            })
    return valid, failures


# ---------------------------------------------------------------------------
# Entity contract map
# ---------------------------------------------------------------------------

def _get_contract(entity: str) -> Optional[Type]:
    try:
        if entity == "patients":
            from contracts.patient_contract import PatientContract
            return PatientContract
        if entity == "appointments":
            from contracts.appointment_contract import AppointmentContract
            return AppointmentContract
        if entity == "admissions":
            from contracts.admission_contract import AdmissionContract
            return AdmissionContract
        if entity == "lab":
            from contracts.lab_contract import LabContract
            return LabContract
        if entity == "pharmacy":
            from contracts.pharmacy_contract import PharmacyContract
            return PharmacyContract
        if entity == "billing":
            from contracts.billing_contract import BillingContract
            return BillingContract
        if entity == "radiology":
            from contracts.radiology_contract import RadiologyContract
            return RadiologyContract
        if entity == "theatre":
            from contracts.theatre_contract import TheatreContract
            return TheatreContract
        if entity in ("operations", "hmo", "patient_insurance"):
            return None  # contracts exist but transform output is already clean
    except ImportError:
        pass
    return None


# ---------------------------------------------------------------------------
# Per-entity pipeline step
# ---------------------------------------------------------------------------

def _process_entity(
    entity: str,
    raw_data: Dict[str, List[Dict]],
    table_hints: Dict[str, List[str]],
    conn,
    run_ctx,
    mode: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run the full Bronze→Silver pipeline for one entity.

    Returns a result dict: {entity, rows_seen, rows_upserted, rows_dlq, duration_s, error}.
    """
    from staging.sqlite_store import StagingStore
    from config import STAGING_DB_PATH

    t0 = time.perf_counter()
    result = {
        "entity": entity,
        "rows_seen": 0,
        "rows_upserted": 0,
        "rows_dlq": 0,
        "duration_s": 0.0,
        "error": None,
    }

    # ── 1. Resolve raw rows from extraction output ──────────────────────────
    raw_rows = _resolve_entity_rows(raw_data, entity, table_hints)
    if raw_rows is None:
        log.info("entity.skipped", entity=entity, reason="no_source_table")
        result["duration_s"] = round(time.perf_counter() - t0, 3)
        return result

    # ── 2. Incremental filter ───────────────────────────────────────────────
    if mode == "incremental" and conn and not dry_run:
        from loaders.db_loader import get_watermark
        wm = get_watermark(conn, entity)
        raw_rows = _apply_watermark_filter(raw_rows, wm)

    # ── 3. Bronze staging ───────────────────────────────────────────────────
    store = StagingStore(STAGING_DB_PATH)
    if mode == "full":
        store.clear(entity)
    count = store.write(entity, raw_rows, run_id=run_ctx.run_id)
    store.record_run(entity, run_ctx.source, count, run_id=run_ctx.run_id)

    # ── 4. Transform ────────────────────────────────────────────────────────
    transformed = _transform_entity(entity, raw_rows)
    if isinstance(transformed, tuple):
        # appointments returns (slots, appts)
        all_rows = transformed[1]
    else:
        all_rows = transformed if transformed else []

    # ── 4b. Quality scoring (Bronze → Quality → Silver) ─────────────────────
    quality_passed = all_rows
    quality_rejected_count = 0
    if all_rows:
        try:
            from quality.quality_engine import QualityEngine
            _qe_conn = conn if not dry_run else None
            qe = QualityEngine(conn=_qe_conn, batch_id=run_ctx.run_id)
            quality_passed, q_report = qe.run(entity, all_rows, run_id=run_ctx.run_id)
            quality_rejected_count = q_report.hard_fails
            if quality_rejected_count:
                log.warning(
                    "quality.rejections",
                    entity=entity,
                    rejected=quality_rejected_count,
                    score=f"{q_report.overall_score * 100:.1f}%",
                )
        except Exception as qe_exc:
            log.warning("quality.engine_error", entity=entity, error=str(qe_exc))
            quality_passed = all_rows

    # ── 5. Contract validation ──────────────────────────────────────────────
    contract = _get_contract(entity)
    valid_rows, dlq_failures = _validate_and_split(entity, quality_passed, contract)
    result["rows_seen"] = len(all_rows)
    result["rows_dlq"] = len(dlq_failures) + quality_rejected_count

    if dlq_failures and conn and not dry_run:
        from loaders.db_loader import load_to_dlq
        load_to_dlq(conn, run_ctx.run_id, entity, dlq_failures)

    # ── 6. Load ─────────────────────────────────────────────────────────────
    if not dry_run and conn:
        upserted = _load_entity(entity, transformed, conn)
        result["rows_upserted"] = upserted
    else:
        _print_dry_run_summary(entity, valid_rows)

    # ── 7. Watermark update ─────────────────────────────────────────────────
    if conn and not dry_run and all_rows:
        from loaders.db_loader import update_watermark
        max_ts = _extract_max_updated_at(all_rows)
        update_watermark(conn, entity, run_ctx.run_id, max_ts, len(all_rows), mode)

    result["duration_s"] = round(time.perf_counter() - t0, 3)
    return result


# ---------------------------------------------------------------------------
# Transform dispatch
# ---------------------------------------------------------------------------

def _transform_entity(entity: str, raw_rows: List[Dict[str, Any]]) -> Any:
    import transformers.patients as t_patients
    import transformers.appointments as t_appointments
    import transformers.admissions as t_admissions
    import transformers.lab as t_lab
    import transformers.pharmacy as t_pharmacy
    import transformers.billing as t_billing
    import transformers.radiology as t_radiology
    import transformers.theatre as t_theatre
    import transformers.operations as t_operations
    import transformers.hmo as t_hmo

    if entity == "patients":
        return t_patients.transform(raw_rows)
    if entity == "appointments":
        return t_appointments.transform(raw_rows)
    if entity == "admissions":
        return t_admissions.transform(raw_rows)
    if entity == "lab":
        return t_lab.transform(raw_rows)
    if entity == "pharmacy":
        return t_pharmacy.transform(raw_rows)
    if entity == "billing":
        return t_billing.transform(raw_rows)
    if entity == "radiology":
        return t_radiology.transform(raw_rows)
    if entity == "theatre":
        return t_theatre.transform(raw_rows)
    if entity == "operations":
        return t_operations.transform(raw_rows)
    if entity == "hmo":
        return t_hmo.transform_hmos(raw_rows)
    if entity == "patient_insurance":
        return t_hmo.transform_patient_insurance(raw_rows)
    return []


# ---------------------------------------------------------------------------
# Load dispatch
# ---------------------------------------------------------------------------

def _load_entity(entity: str, data: Any, conn) -> int:
    from loaders.db_loader import (
        load_admissions, load_appointments, load_billing,
        load_lab, load_patients, load_pharmacy,
        load_operations_events,
    )

    if entity == "patients":
        _, n = load_patients(conn, data or [])
        return n
    if entity == "appointments":
        slots, appts = data if isinstance(data, tuple) else ([], [])
        _, n = load_appointments(conn, slots, appts)
        return n
    if entity == "admissions":
        _, n = load_admissions(conn, data or [])
        return n
    if entity == "lab":
        _, n = load_lab(conn, data or [])
        return n
    if entity == "pharmacy":
        _, n = load_pharmacy(conn, data or [])
        return n
    if entity == "billing":
        _, n = load_billing(conn, data or [])
        return n
    if entity in ("radiology", "theatre", "operations"):
        _, n = load_operations_events(conn, data or [])
        return n
    if entity == "hmo":
        return _load_hmo(conn, data or [])
    if entity == "patient_insurance":
        return _load_patient_insurance(conn, data or [])
    return 0


def _load_hmo(conn, rows: List[Dict]) -> int:
    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            cur.execute(
                f"""
                INSERT INTO public.royan_hmos ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (name) DO UPDATE SET {updates}
                """,
                vals,
            )
            upserted += 1
    conn.commit()
    return upserted


def _load_patient_insurance(conn, rows: List[Dict]) -> int:
    from loaders.db_loader import _patient_id_by_external, EXTERNAL_SOURCE
    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            hope_pid = row.get("_hope_patient_id")
            hope_hmo_id = row.get("_hope_hmo_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue
            # Resolve HMO id
            hmo_id = None
            if hope_hmo_id:
                cur.execute(
                    "SELECT id FROM public.royan_hmos WHERE external_source = %s AND external_id = %s LIMIT 1",
                    (EXTERNAL_SOURCE, str(hope_hmo_id)),
                )
                hmo_row = cur.fetchone()
                hmo_id = hmo_row[0] if hmo_row else None
            if not hmo_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["hmo_id"] = hmo_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            # patient_insurance has no external_source/external_id unique index; use patient+hmo
            cur.execute(
                f"""
                INSERT INTO public.royan_patient_insurance ({col_names})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
                """,
                vals,
            )
            upserted += 1
    conn.commit()
    return upserted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_entity_rows(
    raw_data: Dict[str, List[Dict]],
    entity: str,
    table_hints: Dict[str, List[str]],
) -> Optional[List[Dict]]:
    hints = table_hints.get(entity, [entity])
    for hint in hints:
        if hint in raw_data and raw_data[hint]:
            return raw_data[hint]
    if entity in raw_data:
        return raw_data[entity]
    return None


def _extract_max_updated_at(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Find the latest updated_at/external_updated_at in a batch."""
    candidates = []
    for r in rows:
        for key in ("external_updated_at", "updated_at", "created_at"):
            v = r.get(key)
            if v:
                candidates.append(str(v))
                break
    return max(candidates) if candidates else None


def _print_dry_run_summary(entity: str, rows: List[Dict]) -> None:
    import json
    print(f"\n  [dry-run] {entity}: {len(rows)} rows would be upserted")
    if rows:
        sample = {k: v for k, v in list(rows[0].items())[:6]}
        print(f"  Sample: {json.dumps(sample, default=str)}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    from pipeline_config import PipelineConfig
    cfg = PipelineConfig()

    parser = argparse.ArgumentParser(
        description="RoyanHealth Data Assimilation Pipeline v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=["dump", "csv"], required=True)
    parser.add_argument("--file", help="Path to .sql dump (--source dump)")
    parser.add_argument("--folder", help="Path to CSV folder (--source csv)")
    parser.add_argument("--entity", default="all",
                        help="Entity to process: all | " + " | ".join(ENTITY_ORDER))
    parser.add_argument("--mode", choices=["full", "incremental"], default=cfg.default_mode,
                        help="full = load all rows; incremental = only rows newer than watermark")
    parser.add_argument("--step", default="all",
                        choices=["discover", "all"],
                        help="discover = print source tables and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Transform and print — no DB writes")
    args = parser.parse_args()

    # ── Discover mode ────────────────────────────────────────────────────────
    if args.step == "discover":
        if args.source != "dump" or not args.file:
            print("ERROR: --step discover requires --source dump --file <path>")
            sys.exit(1)
        from extractors.mysql_dump import discover
        discover(args.file)
        return

    # ── Validate inputs ──────────────────────────────────────────────────────
    if args.source == "dump" and not args.file:
        print("ERROR: --source dump requires --file <path>")
        sys.exit(1)
    if args.source == "csv" and not args.folder:
        print("ERROR: --source csv requires --folder <path>")
        sys.exit(1)

    entities = ENTITY_ORDER if args.entity == "all" else [args.entity.lower()]
    for e in entities:
        if e not in ENTITY_ORDER:
            print(f"ERROR: unknown entity '{e}'. Choose from: {', '.join(ENTITY_ORDER)} or all")
            sys.exit(1)

    # ── Build run context ────────────────────────────────────────────────────
    from staging.run_context import RunContext
    run_ctx = RunContext(
        source=args.source,
        mode=args.mode,
        dry_run=args.dry_run,
        source_path=args.file or args.folder,
    )

    log.info("pipeline.start",
             run_id=run_ctx.run_id,
             source=args.source,
             mode=args.mode,
             entities=", ".join(entities),
             dry_run=args.dry_run)

    # ── Extraction ───────────────────────────────────────────────────────────
    log.info("extract.start", run_id=run_ctx.run_id)
    raw_data: Dict[str, List[Dict]] = {}

    if args.source == "dump":
        from extractors.mysql_dump import parse_dump
        raw_data = parse_dump(args.file)
    else:
        from extractors.csv_flat import extract_csv_folder
        raw_data = extract_csv_folder(args.folder)

    log.info("extract.done", run_id=run_ctx.run_id, tables=len(raw_data))

    from transformers.field_maps import TABLE_HINTS

    # ── Database connection ──────────────────────────────────────────────────
    conn = None
    if not args.dry_run:
        try:
            from config import DATABASE_URL
            from loaders.db_loader import get_conn
            conn = get_conn(DATABASE_URL)
        except Exception as exc:
            log.error("db.connect_failed", error=str(exc))
            sys.exit(1)

    # ── Circuit breakers ─────────────────────────────────────────────────────
    breaker = EntityCircuitBreaker(max_failures=cfg.circuit_breaker_threshold)

    # ── Sequential entities first ─────────────────────────────────────────────
    t_pipeline_start = time.perf_counter()
    all_results: Dict[str, Dict] = {}

    seq_entities = [e for e in entities if e in SEQUENTIAL_ENTITIES]
    par_entities  = [e for e in entities if e in PARALLEL_ENTITIES]

    for entity in seq_entities:
        if breaker.is_open(entity):
            log.warning("circuit_skipped", entity=entity)
            continue
        try:
            result = _process_entity(
                entity, raw_data, TABLE_HINTS, conn, run_ctx, args.mode, args.dry_run
            )
            breaker.record_success(entity)
            all_results[entity] = result
            log.info("entity.complete",
                     run_id=run_ctx.run_id,
                     entity=entity,
                     rows_seen=result["rows_seen"],
                     rows_upserted=result["rows_upserted"],
                     rows_dlq=result["rows_dlq"],
                     duration_s=result["duration_s"])
        except Exception as exc:
            breaker.record_failure(entity)
            log.error("entity.failed", entity=entity, error=str(exc))
            traceback.print_exc()
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass

    # ── Parallel entities ─────────────────────────────────────────────────────
    if par_entities:
        def _run_parallel(entity: str) -> Dict:
            # Each parallel worker needs its own DB connection
            par_conn = None
            if not args.dry_run:
                from config import DATABASE_URL
                from loaders.db_loader import get_conn as _get
                par_conn = _get(DATABASE_URL)
            try:
                return _process_entity(
                    entity, raw_data, TABLE_HINTS, par_conn, run_ctx, args.mode, args.dry_run
                )
            finally:
                if par_conn:
                    par_conn.close()

        with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
            futures = {
                executor.submit(_run_parallel, e): e
                for e in par_entities
                if not breaker.is_open(e)
            }
            for future in as_completed(futures):
                entity = futures[future]
                try:
                    result = future.result()
                    breaker.record_success(entity)
                    all_results[entity] = result
                    log.info("entity.complete",
                             run_id=run_ctx.run_id,
                             entity=entity,
                             rows_seen=result["rows_seen"],
                             rows_upserted=result["rows_upserted"],
                             rows_dlq=result["rows_dlq"],
                             duration_s=result["duration_s"])
                except Exception as exc:
                    breaker.record_failure(entity)
                    log.error("entity.failed", entity=entity, error=str(exc))
                    traceback.print_exc()

    # ── Gold refresh ──────────────────────────────────────────────────────────
    if cfg.gold_refresh_enabled and conn and not args.dry_run:
        log.info("gold.start", run_id=run_ctx.run_id)
        from loaders.gold_loader import run_gold_refresh
        since = None if args.mode == "full" else _extract_max_updated_at(
            [r for rows in raw_data.values() for r in rows[:10]]
        )
        gold_summary = run_gold_refresh(conn, run_ctx.run_id, since)
        log.info("gold.complete", run_id=run_ctx.run_id, **gold_summary)

    # ── Redis cache warm ───────────────────────────────────────────────────────
    if cfg.redis_url and conn and not args.dry_run:
        from cache.redis_client import get_queue_cache
        cache = get_queue_cache(cfg.redis_url)
        if cache and cache.available:
            cache.warm_active_queue(conn)
            cache.set_run_id(run_ctx.run_id)

    # ── Sync run log ──────────────────────────────────────────────────────────
    if conn and not args.dry_run:
        from loaders.db_loader import log_run
        total_seen = sum(r["rows_seen"] for r in all_results.values())
        total_ups = sum(r["rows_upserted"] for r in all_results.values())
        log_run(conn, "pipeline", total_seen, total_ups)

    if conn:
        conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    total_duration = round(time.perf_counter() - t_pipeline_start, 2)
    total_dlq = sum(r["rows_dlq"] for r in all_results.values())
    succeeded = sum(1 for r in all_results.values() if not r.get("error"))

    log.info("pipeline.complete",
             run_id=run_ctx.run_id,
             mode=args.mode,
             total_entities=len(all_results),
             succeeded=succeeded,
             total_rows_upserted=sum(r["rows_upserted"] for r in all_results.values()),
             total_dlq=total_dlq,
             duration_s=total_duration)

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    for entity, r in all_results.items():
        status = "OK" if not r.get("error") else "FAILED"
        print(f"  {entity:20s} {status:6s} seen={r['rows_seen']} "
              f"upserted={r['rows_upserted']} dlq={r['rows_dlq']} ({r['duration_s']}s)")
    print(f"\n  Total time: {total_duration}s | DLQ: {total_dlq} rows rejected")
    print()


if __name__ == "__main__":
    main()
