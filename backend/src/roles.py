"""The access roles people can be given on User Access - one list, used by account creation and
role changes (ALLOWED_ROLES), the User Access page (what to offer and what each opens) and HR
(the team a new person starts in).

A person can hold several roles (e.g. nurse + receptionist); access is the union of them, so
never invent a combined role. What each role opens is enforced by the sidebar and route guards
(SynbotUI/client/lib/nav-items.ts) and by each API's own role check; `about` describes it for
the admin assigning it. The staff keys must equal constants.STAFF_ROLES (the royan_staff.role
CHECK constraint) - tests/test_role_taxonomy.py and the assertion below keep them in step.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.constants import STAFF_ROLES

ROLE_CATALOG: List[Dict[str, Any]] = [
    {"key": "doctor", "label": "Doctor", "team": "Doctors",
     "about": "My Dashboard, patients and the full record, queue, consultations, orders, wards, theatre, specialist clinics, MCH."},
    {"key": "nurse", "label": "Nurse", "team": "Nursing",
     "about": "Nursing Station, triage, vitals and medication rounds, wards & beds, front desk, appointments, immunisation."},
    {"key": "pharmacist", "label": "Pharmacist", "team": "Pharmacy",
     "about": "Dispensing, pharmacy inventory and quality control, and stock valuation in Roy Books."},
    {"key": "lab", "label": "Laboratory", "team": "Laboratory",
     "about": "Lab worklist: samples, results and verification."},
    {"key": "radiology", "label": "Radiology", "team": "Radiology",
     "about": "Imaging worklist and report entry."},
    {"key": "physiotherapist", "label": "Physiotherapist", "team": "Physiotherapy",
     "about": "Patients, queue, nursing station and wards for therapy sessions."},
    {"key": "receptionist", "label": "Front desk", "team": "Front Desk",
     "about": "Check-in and registration, appointments, patient search."},
    {"key": "finance", "label": "Finance", "team": "Finance",
     "about": "Roy Books (billing & cashier, HMO claims, receivables, payables, banking, statements, close), Executive overview."},
    {"key": "hr", "label": "HR", "team": "HR",
     "about": "HR: staff records, timesheets, shift roster, leave and payroll."},
    {"key": "ops", "label": "Operations", "team": "Operations",
     "about": "Clinical operations views, procurement & suppliers, audits & maintenance, front desk, wards."},
    {"key": "quality_assurance", "label": "Quality (QA)", "team": "Quality",
     "about": "Quality & safety (incidents, infection control, HEFAMAA), audits, pharmacy QC, compliance."},
    {"key": "hmo", "label": "HMO officer", "team": "HMO",
     "about": "HMO Desk (today's HMO patients, claims forms, signatures, verification), HMO & Coverage, HMO bills and receivables, patients and queue."},
    {"key": "cashier", "label": "Billing & cashier", "team": "Billing",
     "about": "Billing & Cashier (bills, receipts, voids, patient accounts), patients and the queue's 'to pay' list."},
    {"key": "store", "label": "Stores", "team": "Stores",
     "about": "Department stores and central store: stock in, issues, counts and adjustments, reorder plan, pharmacy inventory."},
    {"key": "auditor", "label": "Auditor (read-only)", "team": "Audit",
     "about": "Read-only Roy Books: ledgers, statements, receivables, payables, stock, banking and every report; the executive overview."},
    {"key": "management", "label": "Management (MD / CEO)", "team": "Management",
     "about": "Executive overview, admin dashboard, Roy Books, HR and every clinical view - everything except system administration."},
    {"key": "admin", "label": "Admin", "team": "Admin",
     "about": "Everything, including User Access, registrations, workflow, audit log and settings."},
    {"key": "viewer", "label": "Viewer", "team": "Operations",
     "about": "Own workspace (tasks, clock, messages) and the workstation only."},
]

assert {r["key"] for r in ROLE_CATALOG} == set(STAFF_ROLES) | {"viewer"}, "ROLE_CATALOG must match constants.STAFF_ROLES"

# accepted for accounts created before the catalogue (not offered for new accounts)
LEGACY_ALIASES = {"sales"}

ALLOWED_ROLES = {r["key"] for r in ROLE_CATALOG} | LEGACY_ALIASES
OFFERED_ROLES = {r["key"] for r in ROLE_CATALOG}


def normalize(roles: List[str] | None, *, allow_legacy: bool = False) -> List[str]:
    """Lower-cased, de-duplicated, validated. Unknown roles are an error - never silently dropped.
    'viewer' only stands alone: alongside a real role it adds nothing."""
    values = {r.strip().lower() for r in (roles or []) if isinstance(r, str) and r.strip()}
    if not values:
        return ["viewer"]
    allowed = ALLOWED_ROLES if allow_legacy else OFFERED_ROLES
    bad = sorted(values - allowed)
    if bad:
        raise ValueError(f"Unknown role{'s' if len(bad) > 1 else ''}: {', '.join(bad)}")
    if len(values) > 1:
        values.discard("viewer")
    return sorted(values)
