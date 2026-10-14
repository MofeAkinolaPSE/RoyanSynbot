"""AccountingRuleService: business event -> which accounts.

Modules never hard-code account numbers. They ask for a *role*
(AR_CONTROL, REVENUE_LAB, ...) or a product's own accounts, and the entity's
configuration answers (Setup > Posting rules). When Royan's Sage chart is
loaded, the accountant re-points a role; no code changes.

Hospital adaptation (ACE-Books.md s13): revenue is recognised by service
line, and receivables are split by who owes - the patient's share sits in
AR_CONTROL (patients, corporates, walk-in) and the HMO's share in AR_HMO,
because HMO debt is collected, aged and disputed in a completely different
way from a patient's co-payment.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.fin.accounts import mapped_account, optional_mapped
from src.fin.db import q1
from src.fin.errors import FinError

# role -> description.  Used by Setup > Posting rules.
MAPPING_KEYS: Dict[str, str] = {
    "AR_CONTROL": "Receivables control - patients, corporates and walk-in debtors",
    "AR_HMO": "Receivables control - HMOs and insurers (the payer's share of bills)",
    "AP_CONTROL": "Accounts Payable control (supplier bills)",
    "REVENUE_CONSULTATION": "Consultation fees",
    "REVENUE_LAB": "Laboratory income",
    "REVENUE_RADIOLOGY": "Radiology & imaging income",
    "REVENUE_PHARMACY": "Pharmacy sales (drugs billed to patients)",
    "REVENUE_WARD": "Ward, room & accommodation income",
    "REVENUE_NURSING": "Nursing care income",
    "REVENUE_PROCEDURE": "Surgery, theatre & procedure income",
    "REVENUE_MATERNITY": "Maternity & delivery income",
    "REVENUE_OTHER": "Other medical services (ambulance, consumables, misc)",
    "REVENUE_IMMUNIZATION": "Immunisation / vaccination income",
    "REVENUE_HMO": "Revenue billed to HMOs (the payer's share) - Royan's Sage books this by payer, not by service",
    "SALES_DEFAULT": "Revenue for a stock item with no own revenue account",
    "SERVICE_INCOME": "Revenue for a service line with no service-line rule",
    "DELIVERY_INCOME": "Delivery / transport charges billed (kept out of medical revenue)",
    "OTHER_CHARGE_INCOME": "Other charges billed on invoices",
    "SALES_DISCOUNT": "Discounts allowed (approved bill discounts)",
    "SALES_RETURNS": "Returns & allowances (bill reductions, credit notes)",
    "HMO_DISALLOWANCE": "HMO disallowances (claim amounts the payer refused)",
    "PATIENT_WAIVERS": "Patient waivers & charity care",
    "BAD_DEBTS": "Bad debts written off",
    "INVENTORY_DEFAULT": "Inventory when a product has no own inventory account",
    "COGS_DEFAULT": "Cost of drugs / items dispensed or sold",
    "CONSUMABLES_EXPENSE": "Consumables used internally (ward / theatre consumption)",
    "INVENTORY_ADJUSTMENT": "Stock write-offs / count differences",
    "STOCK_ON_LOAN": "Stock lent to another facility (still ours, not on the shelf)",
    "PURCHASE_EXPENSE_DEFAULT": "Default expense for non-stock supplier bill lines",
    "GOODS_RECEIVED_NOT_INVOICED": "Stock received by the pharmacy, supplier invoice not yet posted (cleared by the bill)",
    "WHT_SUFFERED": "Withholding tax deducted by payers from their payments",
    "WHT_PAYABLE": "Withholding tax deducted from supplier payments (owed to FIRS)",
    "BANK_CHARGES": "Bank charges",
    "SALARIES_EXPENSE": "Salary cost (gross pay, allowances and overtime from HR payroll)",
    "SALARIES_PAYABLE": "Net pay owed to staff (cleared when HR marks payroll paid)",
    "PAYE_PAYABLE": "PAYE deducted from salaries (owed to the State IRS)",
    "PENSION_PAYABLE": "Pension deducted from salaries (owed to the PFA)",
    "PAYROLL_DEDUCTIONS": "Other salary deductions - loans, advances (unset until Finance decides)",
    "RETAINED_EARNINGS": "Retained earnings (year-end close target)",
    "OPENING_BALANCE_EQUITY": "Opening balance equity (migration suspense)",
    "ASSET_DISPOSAL": "Gain / loss on disposal of fixed assets",
    "OUTPUT_TAX": "Tax collected on sales (unset until tax rules are confirmed)",
    "INPUT_TAX": "Tax paid on purchases (unset until tax rules are confirmed)",
}

# Every receivables control account; controls reconcile their sum to the subledger.
AR_KEYS = ("AR_CONTROL", "AR_HMO")

# Bill-item category (royan_bill_items / royan_inpatient_bill_lines) -> revenue role.
CATEGORY_REVENUE = {
    "consultation": "REVENUE_CONSULTATION",
    "lab": "REVENUE_LAB",
    "imaging": "REVENUE_RADIOLOGY",
    "radiology": "REVENUE_RADIOLOGY",
    "pharmacy": "REVENUE_PHARMACY",
    "ward": "REVENUE_WARD",
    "nursing": "REVENUE_NURSING",
    "procedure": "REVENUE_PROCEDURE",
    "surgery": "REVENUE_PROCEDURE",
    "maternity": "REVENUE_MATERNITY",
    "immunisation": "REVENUE_IMMUNIZATION",
    "immunization": "REVENUE_IMMUNIZATION",
    "vaccination": "REVENUE_IMMUNIZATION",
}

# Bill-item category -> fin_departments.code (journal-line department dimension).
CATEGORY_DEPARTMENT = {
    "consultation": "OPD", "lab": "LAB", "imaging": "RAD", "radiology": "RAD", "pharmacy": "PHARM",
    "ward": "IPD", "nursing": "IPD", "procedure": "SURG", "surgery": "SURG", "maternity": "MATERN",
}


def account(conn, entity_id: str, key: str) -> Dict[str, Any]:
    if key not in MAPPING_KEYS:
        raise FinError("VALIDATION_FAILED", f"Unknown posting rule {key}")
    return mapped_account(conn, entity_id, key)


def optional(conn, entity_id: str, key: str) -> Optional[Dict[str, Any]]:
    return optional_mapped(conn, entity_id, key)


def ar_account(conn, entity_id: str, customer_id: Any) -> Dict[str, Any]:
    """The receivables control for this debtor: HMOs to AR_HMO when it is mapped."""
    c = q1(conn, "SELECT party_type FROM fin_customers WHERE id=%s", (int(customer_id),))
    if c and c["party_type"] == "HMO":
        hmo = optional_mapped(conn, entity_id, "AR_HMO")
        if hmo:
            return hmo
    return account(conn, entity_id, "AR_CONTROL")


def revenue_account(conn, entity_id: str, category: Optional[str]) -> Dict[str, Any]:
    """Service-line revenue for a bill category, falling back to the general service income."""
    key = CATEGORY_REVENUE.get((category or "").strip().lower(), "REVENUE_OTHER")
    return optional_mapped(conn, entity_id, key) or account(conn, entity_id, "SERVICE_INCOME")


def department_id(conn, entity_id: str, category: Optional[str]) -> Optional[str]:
    code = CATEGORY_DEPARTMENT.get((category or "").strip().lower())
    if not code:
        return None
    d = q1(conn, "SELECT id FROM fin_departments WHERE legal_entity_id=%s AND code=%s", (entity_id, code))
    return str(d["id"]) if d else None


def product(conn, entity_id: str, sku: str) -> Dict[str, Any]:
    p = q1(conn, "SELECT * FROM fin_products WHERE legal_entity_id=%s AND sku=%s", (entity_id, sku))
    if not p:
        raise FinError("RESOURCE_NOT_FOUND", f"Product {sku} is not in the product list",
                       {"sku": sku})
    return p


def product_accounts(conn, entity_id: str, sku: str) -> Dict[str, Any]:
    """Revenue / inventory / COGS accounts for a product, falling back to defaults."""
    p = product(conn, entity_id, sku)
    out = {"product": p}
    for field, key in (("revenue_account_id", "SALES_DEFAULT"), ("inventory_account_id", "INVENTORY_DEFAULT"),
                       ("cogs_account_id", "COGS_DEFAULT")):
        if p.get(field):
            out[field] = str(p[field])
        else:
            out[field] = str(account(conn, entity_id, key)["id"])
    return out
