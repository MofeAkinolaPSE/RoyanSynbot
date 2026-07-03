"""SIF Hope Connector — Chapter 5 of the Implementation Guide.

Wraps the existing mysql_dump extractor behind the SourceConnector interface.
The connector reads watermarks from royan_hope_sync_runs and yields domain
records in micro-batches for the orchestrator to process.

Hope domain → SIF domain mapping:
    patients      ← PatientRegistration / RegistrationMaster
    encounters    ← OPD / Admission / Ward tables
    lab_orders    ← LabOrders / LabTestMaster
    prescriptions ← Prescriptions / DrugMaster
    billing       ← PatientBilling / BillItems
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import psycopg2
import psycopg2.extras

from sif.connector_base import DOMAINS, SourceConnector

logger = logging.getLogger(__name__)


# Hope SQL dump table → SIF domain mapping
_DOMAIN_TABLE_MAP: Dict[str, List[str]] = {
    "patients": [
        "RegistrationMaster", "PatientRegistration",
        "registration_master", "patient_registration",
    ],
    "encounters": [
        "OPDMaster", "AdmissionMaster", "WardMaster",
        "opd_master", "admission_master", "ward_master",
    ],
    "lab_orders": [
        "LabOrders", "LabTestMaster", "LabOrderMaster",
        "lab_orders", "lab_test_master", "lab_order_master",
    ],
    "prescriptions": [
        "Prescriptions", "DrugMaster", "PrescriptionMaster",
        "prescriptions", "drug_master", "prescription_master",
    ],
    "billing": [
        "PatientBilling", "BillMaster", "BillItems",
        "patient_billing", "bill_master", "bill_items",
    ],
}


class HopeConnector(SourceConnector):
    """Extract records from a DRM Hope MySQL dump file.

    Args:
        dump_path: Filesystem path to the .sql or .sql.gz dump.
        pg_dsn:    PostgreSQL DSN used to read/write watermarks in
                   royan_hope_sync_runs.
        batch_size: Records per micro-batch yielded to the orchestrator.
    """

    SOURCE_SYSTEM = "hope"

    def __init__(
        self,
        dump_path: str,
        pg_dsn: str,
        batch_size: int = 500,
    ) -> None:
        self._dump_path = Path(dump_path)
        self._pg_dsn = pg_dsn
        self._batch_size = batch_size
        self._parsed_data: Optional[Dict[str, List[Dict]]] = None

    # ── Connection ────────────────────────────────────────────────────────────

    def validate_connection(self) -> bool:
        if not self._dump_path.exists():
            logger.error("Hope dump not found: %s", self._dump_path)
            return False
        try:
            conn = psycopg2.connect(self._pg_dsn)
            conn.close()
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            return False
        return True

    # ── Watermark management ──────────────────────────────────────────────────

    def get_watermark(self, domain: str) -> Optional[datetime]:
        try:
            conn = psycopg2.connect(self._pg_dsn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT completed_at FROM public.royan_hope_sync_runs
                    WHERE domain = %s AND status = 'success'
                    ORDER BY completed_at DESC LIMIT 1
                    """,
                    (domain,),
                )
                row = cur.fetchone()
            conn.close()
        except Exception as exc:
            logger.warning("get_watermark failed for domain '%s': %s", domain, exc)
            return None
        return row[0] if row else None

    def set_watermark(self, domain: str, watermark: datetime) -> None:
        try:
            conn = psycopg2.connect(self._pg_dsn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.royan_hope_sync_runs
                        (domain, status, completed_at, source_system)
                    VALUES (%s, 'success', %s, 'hope')
                    """,
                    (domain, watermark),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("set_watermark failed for domain '%s': %s", domain, exc)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _load_dump(self) -> Dict[str, List[Dict]]:
        """Parse dump once and cache. Subsequent calls return cached data."""
        if self._parsed_data is not None:
            return self._parsed_data

        from extractors.mysql_dump import parse_dump

        all_hope_tables = list({
            t for tables in _DOMAIN_TABLE_MAP.values() for t in tables
        })
        logger.info("Parsing Hope dump: %s", self._dump_path)
        self._parsed_data = parse_dump(str(self._dump_path), target_tables=all_hope_tables)
        logger.info(
            "Dump parsed: %d tables found", len(self._parsed_data)
        )
        return self._parsed_data

    def _rows_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Return all rows from the dump tables that map to *domain*."""
        data = self._load_dump()
        rows: List[Dict] = []
        for table_name in _DOMAIN_TABLE_MAP.get(domain, []):
            if table_name in data:
                rows.extend(data[table_name])
                logger.debug("domain=%s table=%s rows=%d", domain, table_name, len(data[table_name]))
        return rows

    # ── Extraction ────────────────────────────────────────────────────────────

    def extract(
        self,
        domain: str,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Yield micro-batches of raw Hope records for *domain*.

        *since* filtering is best-effort on `updated_at` or `created_at` if
        those columns exist in the dump; the orchestrator should still de-dupe
        via the integration.lineage table.
        """
        if domain not in DOMAINS:
            raise ValueError(f"Unknown domain '{domain}'. Valid: {DOMAINS}")

        bs = batch_size or self._batch_size
        all_rows = self._rows_for_domain(domain)

        # Best-effort incremental filtering
        if since:
            filtered = []
            for r in all_rows:
                ts_val = r.get("updated_at") or r.get("created_at") or r.get("reg_date")
                if ts_val is None:
                    filtered.append(r)
                    continue
                try:
                    if isinstance(ts_val, str):
                        from datetime import datetime as dt
                        ts = dt.fromisoformat(ts_val.replace("Z", "+00:00"))
                    elif isinstance(ts_val, datetime):
                        ts = ts_val
                    else:
                        filtered.append(r)
                        continue
                    if ts > since:
                        filtered.append(r)
                except Exception:
                    filtered.append(r)
            all_rows = filtered

        if not all_rows:
            logger.info("HopeConnector: domain=%s since=%s → 0 rows", domain, since)
            return

        logger.info(
            "HopeConnector: domain=%s rows=%d batch_size=%d", domain, len(all_rows), bs
        )

        for i in range(0, len(all_rows), bs):
            yield all_rows[i : i + bs]

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._parsed_data = None

    def describe(self) -> Dict[str, Any]:
        return {
            "source_system": self.SOURCE_SYSTEM,
            "dump_path": str(self._dump_path),
            "dump_exists": self._dump_path.exists(),
        }
