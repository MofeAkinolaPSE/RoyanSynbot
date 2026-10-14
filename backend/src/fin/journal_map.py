"""Which book of original entry (Sage journal code) each posting belongs to.

The one table the General Ledger's "Jrnl" column and the Journals-by-type reports both read, so a
posting is listed in exactly one journal and carries that label everywhere. The database function
fin_journal_code() (migration 229, used by fin_v_ledger) is the same table in SQL; a test checks
the two agree for every source type below.

Royan's own postings: a hospital bill is a sales invoice (SJ); dispensing a drug is the cost of
goods sold (COGS); goods received into the pharmacy are a purchase (PJ); payroll is a general
journal and its payment a cash disbursement. Bank vouchers follow Sage: money paid out is a cash
disbursement, money received a cash receipt, a transfer between banks a general journal entry.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

SOURCE_JOURNAL: Dict[str, str] = {
    "SALES_INVOICE": "SJ", "CREDIT_NOTE": "SJ",
    "CUSTOMER_RECEIPT": "CRJ",
    "SUPPLIER_BILL": "PJ", "DEBIT_NOTE": "PJ", "PHARMACY_RECEIPT": "PJ",
    "SUPPLIER_PAYMENT": "CDJ", "CUSTOMER_REFUND": "CDJ", "PAYROLL_PAYMENT": "CDJ", "CASH_VOUCHER": "CDJ",
    "DISPENSING": "COGS", "DISPENSE_RETURN": "COGS",
    "STOCK_ADJUSTMENT": "INAJ", "STOCK_COUNT": "INAJ", "STOCK_LOAN": "INAJ", "STOCK_LOAN_RETURN": "INAJ",
    "STOCK_LOAN_WRITEOFF": "INAJ", "PHARMACY_ADJUST": "INAJ", "DEPT_STOCK": "INAJ",
    "FIXED_ASSET": "FA", "DEPRECIATION_RUN": "FA", "FIXED_ASSET_DISPOSAL": "FA",
    "MANUAL_JOURNAL": "GENJ", "MIGRATION": "GENJ", "YEAR_END": "GENJ", "PAYROLL": "GENJ",
    "DATA_CORRECTION": "ADJ",
}
VOUCHER_JOURNAL = {"SPEND": "CDJ", "RECEIVE": "CRJ", "TRANSFER": "GENJ"}
DEFAULT = "GENJ"

# The Journals-by-type reports, in the order the screen lists them.
KEY_CODE = {"sales": "SJ", "cash-receipts": "CRJ", "cash-disbursements": "CDJ", "purchases": "PJ", "cogs": "COGS",
            "general": "GENJ", "inventory-adjustments": "INAJ", "assets": "FA"}
KEY_TITLE = {"sales": "Sales Journal", "cash-receipts": "Cash Receipts Journal", "cash-disbursements": "Cash Disbursements Journal",
             "purchases": "Purchase Journal", "cogs": "Cost of Goods Sold Journal", "general": "General Journal",
             "inventory-adjustments": "Inventory Adjustment Journal", "assets": "Fixed Assets Journal"}

# The journal report each code is listed in: corrections (ADJ) sit in the General Journal, as in Sage.
REPORT_CODES = {"SJ": ("SJ",), "CRJ": ("CRJ",), "PJ": ("PJ",), "CDJ": ("CDJ",), "COGS": ("COGS",), "INAJ": ("INAJ",),
                "FA": ("FA",), "GENJ": ("GENJ", "ADJ")}


def journal_code(source_type: Optional[str], voucher_kind: Optional[str] = None) -> str:
    if source_type == "CASH_VOUCHER" and voucher_kind:
        return VOUCHER_JOURNAL.get(voucher_kind, "CDJ")
    return SOURCE_JOURNAL.get(source_type or "", DEFAULT)


def report_codes(code: str) -> Tuple[str, ...]:
    return REPORT_CODES.get(code, (code,))


def function_sql() -> str:
    """The CREATE FUNCTION for fin_journal_code - how migration 229's body was produced."""
    voucher = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in VOUCHER_JOURNAL.items())
    by_source = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in SOURCE_JOURNAL.items())
    return ("CREATE OR REPLACE FUNCTION fin_journal_code(p_source_type TEXT, p_source_id TEXT) RETURNS TEXT\n"
            "LANGUAGE sql STABLE AS $$\n"
            f"  SELECT CASE WHEN p_source_type='CASH_VOUCHER' THEN COALESCE((SELECT CASE v.kind {voucher} END\n"
            "              FROM fin_cash_vouchers v WHERE v.id::text = p_source_id), 'CDJ')\n"
            f"         ELSE CASE COALESCE(p_source_type, '') {by_source} ELSE '{DEFAULT}' END END\n$$;")
