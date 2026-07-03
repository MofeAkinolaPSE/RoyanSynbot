"""Synbot Integration Framework — Connector Base Class (Chapter 5).

All source system connectors must inherit from SourceConnector and implement
the four abstract methods. The SIF orchestrator calls these methods through
the common interface, so swapping source systems requires no orchestrator changes.

Usage:
    class MyConnector(SourceConnector):
        SOURCE_SYSTEM = "my_system"
        ...
"""
from __future__ import annotations

import abc
import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


class SourceConnector(abc.ABC):
    """Abstract base for all SIF source-system connectors.

    A connector knows how to:
      1. Validate its connection to the source system.
      2. Track the high-water mark (watermark) so each batch only fetches
         new/changed records.
      3. Extract records domain-by-domain as iterables of raw dicts.
      4. Report basic statistics for the orchestrator's run summary.
    """

    SOURCE_SYSTEM: str = "unknown"

    # ── Connection ────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def validate_connection(self) -> bool:
        """Return True if the source system is reachable and healthy."""

    # ── Watermark management ──────────────────────────────────────────────────

    @abc.abstractmethod
    def get_watermark(self, domain: str) -> Optional[datetime]:
        """Return the last-synced watermark for *domain*, or None if fresh start."""

    @abc.abstractmethod
    def set_watermark(self, domain: str, watermark: datetime) -> None:
        """Persist the high-water mark after a successful domain batch."""

    # ── Extraction ────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def extract(
        self,
        domain: str,
        since: Optional[datetime] = None,
        batch_size: int = 500,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Yield lists of raw source records for *domain*.

        Each yielded list is one micro-batch (up to *batch_size* records).
        The caller processes each micro-batch before the next one is yielded,
        so large extracts do not need to fit in memory.

        Args:
            domain: One of "patients", "encounters", "lab_orders",
                    "prescriptions", "billing".
            since: Only return records modified after this timestamp.
                   None = full extract from the beginning.
            batch_size: Maximum records per micro-batch.
        """

    # ── Statistics ────────────────────────────────────────────────────────────

    def describe(self) -> Dict[str, Any]:
        """Return connector metadata for run-summary logging."""
        return {"source_system": self.SOURCE_SYSTEM}

    def close(self) -> None:
        """Release any held connections / file handles. Called after extract."""


# ── Domain constants used by all connectors ──────────────────────────────────

DOMAINS: List[str] = [
    "patients",
    "encounters",
    "lab_orders",
    "prescriptions",
    "billing",
]
