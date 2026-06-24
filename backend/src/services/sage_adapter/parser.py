"""
Sage adapter parser stub — Placeware/pharma import pipeline removed.

Provides parse_tabular_upload so that existing callers in app.py compile
without the original Sage CSV/Excel parsing infrastructure.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def parse_tabular_upload(
    content: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Parse uploaded tabular file bytes into a list of row dicts.

    Stub: returns an empty list — Sage import pipeline is not active.
    """
    return []
