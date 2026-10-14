"""Request context: who is acting, for which legal entity, with what rights.

Every Roy Books query is scoped by `ctx.entity_id`; the frontend never
supplies isolation, it only *requests* an entity (X-Legal-Entity header) and
the backend resolves and enforces it.
"""
from __future__ import annotations

import fnmatch
import uuid
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

from fastapi import Request

from src.fin.db import q1
from src.fin.errors import FinError
from src.middleware import verify_jwt

# domain.resource.action (Backend & Frontend spec §30). Wildcards allowed.
ROLE_PERMISSIONS = {
    "admin": {"*"},
    # The hospital's accountants: full day-to-day bookkeeping. Reopening a
    # closed period and changing posting policy stay with admin/management.
    "finance": {
        "*.view", "accounting.*", "sales.*", "receivables.*", "payables.*",
        "inventory.*", "banking.*", "assets.*", "budget.*", "reports.*",
        "controls.*", "finance.period.close", "migration.*",
    },
    "management": {
        "*.view", "reports.*", "accounting.journal.approve", "sales.credit.override",
        "inventory.adjustment.approve", "finance.period.close", "finance.period.reopen",
        "finance.settings.edit", "budget.approve", "controls.*",
    },
    # Pharmacy owns the drug stock: it counts, adjusts (a second person
    # approves), quarantines batches and raises recalls through Roy Books.
    "pharmacist": {"inventory.view", "inventory.adjustment.create", "inventory.count.create",
                   "inventory.recall.create", "inventory.batch.edit", "reports.view", "payables.view"},
    # Quality assurance acts on stock through Roy Books: recalls (batch frozen, patients traced),
    # batch release/quarantine and expiry write-offs (a second person approves those).
    "quality_assurance": {"inventory.view", "inventory.recall.create", "inventory.batch.edit",
                          "inventory.adjustment.create", "reports.view"},
    # Operations / procurement read supplier bills and balances but do not record them.
    "ops": {"inventory.view", "reports.view", "payables.view"},
    "procurement": {"inventory.view", "reports.view", "payables.view"},
    # HMO officers follow their patients' bills, claims and what each HMO owes; they record nothing in the ledger.
    "hmo": {"sales.view", "receivables.view", "reports.view"},
    # The cashier takes and voids receipts; everything else is read.
    "cashier": {"sales.view", "receivables.view", "receivables.receipt.create", "receivables.receipt.void",
                "banking.view", "reports.view"},
    # Stores keep the department and central stock: receive, issue, count and adjust (a second person approves).
    "store": {"inventory.view", "inventory.adjustment.create", "inventory.count.create", "inventory.loan.create",
              "inventory.product.create", "payables.view", "reports.view"},
    # Internal / external auditors: see everything, change nothing.
    "auditor": {"*.view", "reports.view"},
}


@dataclass
class FinContext:
    actor_id: str
    actor_name: str
    roles: List[str]
    entity_id: str
    permissions: Set[str] = field(default_factory=set)
    request_id: str = ""
    ip: Optional[str] = None

    def can(self, permission: str) -> bool:
        for granted in self.permissions:
            if granted == "*" or fnmatch.fnmatchcase(permission, granted):
                return True
        return False

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise FinError("PERMISSION_DENIED", f"You do not have permission: {permission}",
                           {"permission": permission})


def permissions_for(roles: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for r in roles:
        out |= ROLE_PERMISSIONS.get(str(r).lower(), set())
    return out


def resolve_entity(conn, requested: Optional[str]) -> str:
    if requested:
        try:
            uuid.UUID(requested)
            row = q1(conn, "SELECT id FROM fin_legal_entities WHERE id = %s AND status='ACTIVE'", (requested,))
        except ValueError:
            row = q1(conn, "SELECT id FROM fin_legal_entities WHERE code = %s AND status='ACTIVE'", (requested,))
        if not row:
            # Never fall back to another company's books.
            raise FinError("RESOURCE_NOT_FOUND", f"Legal entity not found: {requested}")
        return str(row["id"])
    row = q1(conn, "SELECT id FROM fin_legal_entities WHERE status='ACTIVE' ORDER BY created_at LIMIT 1")
    if not row:
        raise FinError("RESOURCE_NOT_FOUND", "No legal entity is set up yet")
    return str(row["id"])


def build_context(request: Request, conn) -> FinContext:
    payload = verify_jwt(request)
    roles = [str(r).lower() for r in (payload.get("roles") or [])]
    perms = permissions_for(roles)
    if not perms:
        raise FinError("PERMISSION_DENIED", "Your role has no access to Roy Books")
    actor = str(payload.get("sub") or "unknown")
    name = payload.get("name") or payload.get("email") or actor
    entity = resolve_entity(conn, request.headers.get("X-Legal-Entity"))
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    ip = request.client.host if request.client else None
    return FinContext(actor, str(name), roles, entity, perms, rid, ip)


def system_context(conn, entity_id: Optional[str] = None, actor: str = "system") -> FinContext:
    """For postings triggered by hospital operations (billing, cashier, pharmacy)."""
    return FinContext(actor, actor, ["admin"], entity_id or resolve_entity(conn, None), {"*"}, uuid.uuid4().hex[:16])
