from __future__ import annotations

from typing import List, Dict, Any
from typing import Any as DBClient
from ..db import db
from .sage_adapter.service import get_sage_kpi_batch_id


def rolling_average(values: List[float], window: int = 3) -> List[float]:
    if window <= 0:
        return []
    out: List[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start : i + 1]
        out.append(sum(window_vals) / len(window_vals))
    return out


def ar_balance_series(client: DBClient = db, max_points: int = 12) -> List[Dict[str, Any]]:
    # Sage AR snapshot removed — hospital billing series should use royan_billing
    return []


def forecast_ar_balance(client: DBClient = db, window: int = 3, horizon: int = 3) -> Dict[str, Any]:
    series = ar_balance_series(client=client, max_points=12)
    balances = [p["balance"] for p in series]
    if not balances:
        return {"series": [], "rolling": [], "forecast": []}
    roll = rolling_average(balances, window=window)
    # naive forecast: extend last rolling average for horizon steps
    last = roll[-1]
    forecast = [last for _ in range(horizon)]
    return {"series": series, "rolling": roll, "forecast": forecast}
