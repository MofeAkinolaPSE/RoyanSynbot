"""
Sage adapter schemas stub — Placeware/pharma import pipeline removed.

Provides the ImportBundle and ImportMeta types so that existing callers
in app.py continue to compile and type-check without the original Sage
import infrastructure. All row models return safe zero-defaults.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Row-level models (minimal — only attributes accessed by app.py logic)
# ---------------------------------------------------------------------------

@dataclass
class ArRow:
    amount:  Optional[float] = None
    balance: Optional[float] = None


@dataclass
class ApRow:
    amount:  Optional[float] = None
    balance: Optional[float] = None


@dataclass
class GlRow:
    debit:  Optional[float] = None
    credit: Optional[float] = None
    period: Any = None


@dataclass
class CustomerRow:
    pass


@dataclass
class InventoryRow:
    pass


@dataclass
class StaffRow:
    pass


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------

@dataclass
class ImportMeta:
    source_system: str = "sage50"
    imported_by:   str = ""
    notes:         str = ""
    client_ref:    str = ""


@dataclass
class ImportBundle:
    meta:       ImportMeta               = field(default_factory=ImportMeta)
    customers:  List[CustomerRow]        = field(default_factory=list)
    ar:         List[ArRow]              = field(default_factory=list)
    ap:         List[ApRow]              = field(default_factory=list)
    gl:         List[GlRow]              = field(default_factory=list)
    inventory:  List[InventoryRow]       = field(default_factory=list)
    staff:      List[StaffRow]           = field(default_factory=list)
