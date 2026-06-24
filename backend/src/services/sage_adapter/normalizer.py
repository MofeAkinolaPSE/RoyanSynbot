"""
Sage adapter normalizer stub — Placeware/pharma import pipeline removed.

Provides row-normalizer functions so that existing callers in app.py compile
without the original Sage data-normalisation infrastructure. Each function
accepts a list of raw row dicts and returns an empty list — the import
pipeline endpoints are dead code paths in the hospital deployment.
"""
from __future__ import annotations
from typing import Any, Dict, List


def to_customers(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise customer rows. Stub: returns empty list."""
    return []


def to_ar(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise AR rows. Stub: returns empty list."""
    return []


def to_ap(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise AP rows. Stub: returns empty list."""
    return []


def to_gl(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise GL rows. Stub: returns empty list."""
    return []


def to_inventory(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise inventory rows. Stub: returns empty list."""
    return []


def to_staff(rows: List[Dict[str, Any]]) -> List[Any]:
    """Normalise staff rows. Stub: returns empty list."""
    return []
