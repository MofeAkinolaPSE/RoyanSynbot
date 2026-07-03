"""Excel / XLS importer for Hope pharmacy and service catalog data.

Reads XLSX (openpyxl) or legacy XLS (xlrd) files exported from DRM Hope and
loads them into royan_service_catalog in PostgreSQL.

Supported source files from DrM File/:
  - ITEM1.xlsx / ITEMNEW.xlsx      → pharmacy drug catalog
  - STOCK pharmacy.xlsx            → pharmacy inventory (stock levels)
  - Laboratory Charges Of *.xls    → lab service prices
  - Service Charges Of *.xls       → general service prices
  - Radiology Charges Of *.xls     → imaging service prices
  - Pharmacy Charges Of *.xls      → HMO pharmacy tariffs

Usage:
    # See column names without writing anything:
    python scripts/load_excel.py --file "DrM File/ITEM1.xlsx" --discover

    # Load drug catalog:
    python scripts/load_excel.py --file "DrM File/ITEM1.xlsx" --category pharmacy

    # Load lab HMO charges:
    python scripts/load_excel.py --file "DrM File/lab_charges.xls" --category lab

    # Load all XLSX/XLS from a folder:
    python scripts/load_excel.py --folder "DrM File/RhosP/app/webroot/uploads/import"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Category auto-detection from filename
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: Dict[str, str] = {
    "lab":          "lab",
    "laboratory":   "lab",
    "radiology":    "imaging",
    "imaging":      "imaging",
    "xray":         "imaging",
    "pharmacy":     "pharmacy",
    "drug":         "pharmacy",
    "item":         "pharmacy",
    "service":      "misc",
    "surgery":      "procedure",
    "theatre":      "procedure",
    "ward":         "ward",
    "consultation": "consultation",
}

VALID_CATEGORIES = {"consultation", "lab", "pharmacy", "ward", "procedure", "imaging", "misc"}


def _detect_category(filepath: str) -> str:
    """Guess category from filename."""
    name = Path(filepath).stem.lower()
    for keyword, cat in CATEGORY_KEYWORDS.items():
        if keyword in name:
            return cat
    return "misc"


# ---------------------------------------------------------------------------
# Excel reading (handles both .xlsx and .xls)
# ---------------------------------------------------------------------------

def read_excel(filepath: str) -> List[Dict[str, Any]]:
    """Return all rows as a list of dicts with lowercase column names."""
    ext = Path(filepath).suffix.lower()
    if ext == ".xlsx":
        return _read_xlsx(filepath)
    elif ext in (".xls", ".xlsm"):
        return _read_xls(filepath)
    else:
        raise ValueError(f"Unsupported extension: {ext}")


def _read_xlsx(filepath: str) -> List[Dict[str, Any]]:
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl not installed. Run: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    headers = [str(h).strip().lower().replace(" ", "_") if h is not None else f"col_{i}"
               for i, h in enumerate(rows[0])]
    return [
        {headers[i]: cell for i, cell in enumerate(row) if i < len(headers)}
        for row in rows[1:]
        if any(cell is not None for cell in row)
    ]


def _read_xls(filepath: str) -> List[Dict[str, Any]]:
    try:
        import xlrd
    except ImportError:
        print("ERROR: xlrd not installed. Run: pip install xlrd")
        sys.exit(1)

    wb = xlrd.open_workbook(filepath)
    ws = wb.sheet_by_index(0)

    if ws.nrows < 2:
        return []

    headers = [str(ws.cell_value(0, c)).strip().lower().replace(" ", "_")
               for c in range(ws.ncols)]
    rows = []
    for r in range(1, ws.nrows):
        row_vals = [ws.cell_value(r, c) for c in range(ws.ncols)]
        if any(v != "" and v is not None for v in row_vals):
            rows.append({headers[i]: v for i, v in enumerate(row_vals)})
    return rows


# ---------------------------------------------------------------------------
# Column name normalization
# ---------------------------------------------------------------------------

# Maps common Hope Excel column names → service catalog fields
COLUMN_MAP = {
    # Drug name / service name
    "drug_name":        "name",
    "item_name":        "name",
    "name":             "name",
    "description":      "name",
    "service":          "name",
    "service_name":     "name",
    "test_name":        "name",
    "investigation":    "name",

    # Code
    "drug_code":        "service_code",
    "code":             "service_code",
    "item_code":        "service_code",
    "service_code":     "service_code",
    "nafdac":           "service_code",
    "nafdac_no":        "service_code",

    # Price
    "price":            "base_price",
    "amount":           "base_price",
    "cost":             "base_price",
    "rate":             "base_price",
    "charge":           "base_price",
    "unit_price":       "base_price",
    "selling_price":    "base_price",
    "selling_cost":     "base_price",
    "tariff":           "base_price",
    "fee":              "base_price",

    # Active flag
    "is_active":        "is_active",
    "active":           "is_active",
    "status":           "is_active",
}


def normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map raw Excel row → service catalog fields."""
    out: Dict[str, Any] = {}
    for col, val in raw.items():
        target = COLUMN_MAP.get(col)
        if target and target not in out:
            out[target] = val
    return out


def _safe_price(val: Any) -> float:
    try:
        return float(str(val).replace(",", "")) if val not in (None, "", "N/A") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_code(val: Any, fallback: str) -> str:
    s = str(val).strip() if val is not None else ""
    return s[:100] if s else fallback


def _safe_name(val: Any) -> Optional[str]:
    s = str(val).strip() if val is not None else ""
    return s[:255] if s else None


def _is_active(val: Any) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return s not in {"0", "false", "inactive", "no", "n"}


# ---------------------------------------------------------------------------
# PostgreSQL loader
# ---------------------------------------------------------------------------

def load_to_db(rows: List[Dict[str, Any]], category: str, dry_run: bool = False) -> int:
    """Upsert service catalog rows into PostgreSQL. Returns count inserted/updated."""
    if not rows:
        return 0

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import DATABASE_URL
        import psycopg2
    except (ImportError, EnvironmentError) as exc:
        print(f"ERROR: {exc}")
        print("Run from data-assimilation/ with DATABASE_URL set in .env")
        return 0

    upserted = 0
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for i, row in enumerate(rows):
                name = _safe_name(row.get("name"))
                if not name:
                    continue

                # Generate service_code from name if not provided
                raw_code = row.get("service_code")
                code = _safe_code(raw_code, f"{category.upper()[:3]}-{i:04d}")

                price = _safe_price(row.get("base_price"))
                active = _is_active(row.get("is_active"))

                if dry_run:
                    print(f"  [DRY] {code!r:20s}  {name[:50]!r:52s}  {category}  £{price:.2f}")
                    upserted += 1
                    continue

                cur.execute("""
                    INSERT INTO public.royan_service_catalog
                        (service_code, name, category, base_price, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (service_code) DO UPDATE SET
                        name       = EXCLUDED.name,
                        base_price = EXCLUDED.base_price,
                        is_active  = EXCLUDED.is_active,
                        updated_at = now()
                """, (code, name, category, price, active))
                upserted += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return upserted


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _process_file(filepath: str, category: Optional[str], discover: bool, dry_run: bool) -> None:
    print(f"\n  File: {filepath}")
    try:
        raw_rows = read_excel(filepath)
    except Exception as exc:
        print(f"  ERROR reading file: {exc}")
        return

    print(f"  Rows read: {len(raw_rows)}")

    if discover or not raw_rows:
        if raw_rows:
            print("  Columns found:")
            for col in raw_rows[0].keys():
                sample = raw_rows[0].get(col)
                print(f"    - {col!r:35s}  e.g. {repr(str(sample)[:40])}")
        else:
            print("  (empty file)")
        return

    cat = category or _detect_category(filepath)
    if cat not in VALID_CATEGORIES:
        print(f"  WARNING: unknown category {cat!r}, using 'misc'")
        cat = "misc"

    normalized = [normalize_row(r) for r in raw_rows]
    named = [r for r in normalized if r.get("name")]

    print(f"  Category: {cat}  |  Rows with name: {len(named)}")
    count = load_to_db(named, cat, dry_run=dry_run)
    action = "would upsert" if dry_run else "upserted"
    print(f"  {count} rows {action}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Hope Excel files → royan_service_catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to a single XLSX or XLS file")
    group.add_argument("--folder", help="Process all XLSX/XLS files in a folder")

    parser.add_argument(
        "--category",
        choices=list(VALID_CATEGORIES),
        help="Override category (default: auto-detect from filename)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Print column names without loading",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be loaded without writing to DB",
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Hope Excel → royan_service_catalog")
    print(f"{'='*60}")

    if args.file:
        _process_file(args.file, args.category, args.discover, args.dry_run)
    else:
        folder = Path(args.folder)
        files = sorted(folder.glob("**/*.xlsx")) + sorted(folder.glob("**/*.xls"))
        if not files:
            print(f"No XLSX/XLS files found in {folder}")
            return
        print(f"Found {len(files)} files in {folder}\n")
        for f in files:
            _process_file(str(f), args.category, args.discover, args.dry_run)

    print(f"\n{'='*60}")
    print("Done.\n")


if __name__ == "__main__":
    main()
