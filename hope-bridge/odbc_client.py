"""
hope-bridge/odbc_client.py
--------------------------
ODBC read layer for DRM Hope database.
All functions are stubs until the first site visit confirms:
  - The ODBC DSN name (registered in Windows ODBC Data Source Administrator)
  - The database backend (MSSQL / MySQL)
  - The table names for patients, appointments, admissions, pharmacy, lab, billing

To discover the schema on site, run:
    python odbc_client.py --discover

References (briefing §6.2):
  - pyodbc DSN pattern: pyodbc.connect(f"DSN={dsn};Trusted_Connection=yes")
  - Key tables to map: patients, admissions, wards, pharmacy_orders, billing,
    staff, appointments
"""
from __future__ import annotations

import argparse
import os
import logging
from typing import Any

log = logging.getLogger(__name__)

# ── Connection ────────────────────────────────────────────────────────────────

def get_connection():  # pragma: no cover
    """
    Return a live pyodbc connection to the DRM Hope database.

    Requires pyodbc to be installed and the HOPE_ODBC_DSN to be registered
    in Windows ODBC Data Source Administrator (64-bit).

    TODO: Confirm DSN name and driver on first site visit.
    """
    try:
        import pyodbc  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "pyodbc is not installed. Run: pip install pyodbc"
        ) from exc

    dsn = os.getenv("HOPE_ODBC_DSN")
    if not dsn:
        raise RuntimeError(
            "HOPE_ODBC_DSN environment variable is not set. "
            "Register the DRM Hope ODBC DSN in Windows and set the variable."
        )
    return pyodbc.connect(f"DSN={dsn};Trusted_Connection=yes")


# ── Schema discovery (run on first site visit) ────────────────────────────────

def discover_tables() -> list[str]:  # pragma: no cover
    """Return all table names in the Hope database. Run once on site."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
        )
        return [row[0] for row in cur.fetchall()]


def sample_table(table_name: str, n: int = 5) -> list[dict[str, Any]]:  # pragma: no cover
    """Return first `n` rows of a table as dicts. Use to map column names."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT TOP {int(n)} * FROM [{table_name}]")  # noqa: S608
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Data fetch stubs ──────────────────────────────────────────────────────────
# Each function below is a STUB.  After the site visit, replace the body with
# a real ODBC query using the confirmed table/column names.

def fetch_patients(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query after confirming Hope patient table name.
    Expected columns: patient_id, mrn, first_name, last_name, dob, gender,
                      phone, blood_group, hmo, updated_at
    """
    raise NotImplementedError(
        "fetch_patients: ODBC table name not yet confirmed. "
        "Set HOPE_MOCK=1 or complete the site visit first."
    )


def fetch_appointments(
    date_from: str | None = None,
    date_to:   str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query after confirming Hope appointment table name.
    Expected columns: appointment_id, patient_id, doctor, department,
                      slot_date, slot_time, status
    """
    raise NotImplementedError("fetch_appointments: ODBC table name not yet confirmed.")


def fetch_admissions(active_only: bool = True) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query.
    Expected columns: admission_id, patient_id, ward, bed, admitted_at,
                      discharged_at, diagnosis, consultant
    """
    raise NotImplementedError("fetch_admissions: ODBC table name not yet confirmed.")


def fetch_pharmacy_orders(
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query.
    Expected columns: order_id, patient_id, drug, quantity, unit,
                      status, ordered_at
    """
    raise NotImplementedError("fetch_pharmacy_orders: ODBC table name not yet confirmed.")


def fetch_lab_orders(
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query.
    Expected columns: order_id, patient_id, test, status, ordered_at,
                      resulted_at, result_summary
    """
    raise NotImplementedError("fetch_lab_orders: ODBC table name not yet confirmed.")


def fetch_billing(
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    TODO: Replace with real query.
    Expected columns: invoice_id, patient_id, total_amount, hmo_claim,
                      patient_due, currency, status, created_at
    """
    raise NotImplementedError("fetch_billing: ODBC table name not yet confirmed.")


# ── CLI helper ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DRM Hope ODBC discovery tool")
    parser.add_argument("--discover",   action="store_true", help="List all tables")
    parser.add_argument("--sample",     metavar="TABLE",     help="Show 5 rows from TABLE")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.discover:
        tables = discover_tables()
        print(f"\nFound {len(tables)} tables:\n")
        for t in tables:
            print(f"  {t}")

    elif args.sample:
        rows = sample_table(args.sample)
        import json
        print(json.dumps(rows, indent=2, default=str))

    else:
        parser.print_help()
