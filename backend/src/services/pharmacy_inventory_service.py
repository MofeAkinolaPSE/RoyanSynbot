"""Pharmacy Inventory Service — batch/lot stock, risk tiers, demand velocity.

Domain logic for the Pharmacy Inventory workspace: FEFO batch deduction,
demand-velocity computation from real prescribing history, risk-tier
classification (CRITICAL/WARNING/MONITOR/ADEQUATE), and workspace KPI
aggregation. Split out of pharmacy_dispensing.py because Inventory is now
its own workspace, not a Dispensing tab.

Risk-tier math is deliberately rule-based (coverage days vs. lead time +
safety buffer), matching this codebase's existing heuristic-agent style
rather than introducing an ML dependency.
"""
from __future__ import annotations

import datetime as _dt

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.db import db
from src.cache import ttl_cache, invalidate_cache_tags
from src.constants import (
    TABLE_DRUG_FORMULARY, TABLE_INVENTORY_BATCHES, TABLE_DISPENSING,
    TABLE_PRESCRIPTIONS, TABLE_REPLENISHMENT_REQUESTS,
    PHARMACY_DEFAULT_LEAD_TIME_DAYS, PHARMACY_DEFAULT_SAFETY_STOCK_DAYS,
    PHARMACY_REVIEW_CYCLE_DAYS, PHARMACY_DEMAND_WINDOW_DAYS, PHARMACY_EXPIRING_SOON_DAYS,
)

_CACHE_TAGS = ("pharmacy", "inventory")

logger = logging.getLogger(__name__)

_TIER_ORDER = {"CRITICAL": 0, "WARNING": 1, "MONITOR": 2, "ADEQUATE": 3}


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────

def _q(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = db.pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description is not None else []
        conn.commit()
        return rows
    except Exception:
        # A failed query aborts the connection's transaction — roll back so
        # the pooled connection isn't handed back to another caller broken.
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        db.pool.putconn(conn)


def _q1(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _q(sql, params)
    return rows[0] if rows else None


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────────────────

def resolve_formulary_id(drug_name: Optional[str], formulary_id: Optional[int] = None) -> Optional[int]:
    if formulary_id:
        return formulary_id
    if not drug_name or not drug_name.strip():
        return None
    row = _q1(
        f"""SELECT id FROM public.{TABLE_DRUG_FORMULARY}
            WHERE lower(generic_name) = lower(%s) OR lower(brand_name) = lower(%s) OR lower(code) = lower(%s)
            LIMIT 1""",
        (drug_name.strip(), drug_name.strip(), drug_name.strip()),
    )
    return row["id"] if row else None


def _generate_drug_code(generic_name: str) -> str:
    """royan_drug_formulary.code is NOT NULL — synthesize a readable code
    from the drug name when the caller doesn't supply one, rather than
    forcing every ad hoc "add drug" call to invent a product code."""
    base = "".join(ch for ch in generic_name.upper() if ch.isalnum())[:12] or "DRUG"
    candidate = base
    suffix = 1
    while _q1(f"SELECT id FROM public.{TABLE_DRUG_FORMULARY} WHERE code = %s", (candidate,)):
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def upsert_formulary_drug(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a formulary row, or return the existing one if a matching code
    or generic_name is already catalogued (add-drug is idempotent)."""
    code = (payload.get("code") or "").strip() or None
    generic_name = (payload.get("generic_name") or "").strip() or None

    existing = None
    if code:
        resp = db.table(TABLE_DRUG_FORMULARY).select("*").ilike("code", code).limit(1).execute()
        existing = resp.data[0] if resp.data else None
    if not existing and generic_name:
        resp = db.table(TABLE_DRUG_FORMULARY).select("*").ilike("generic_name", generic_name).limit(1).execute()
        existing = resp.data[0] if resp.data else None
    if existing:
        return existing

    data = {k: v for k, v in payload.items() if v is not None and v != ""}
    if not data.get("code"):
        data["code"] = _generate_drug_code(generic_name or "DRUG")
    result = db.table(TABLE_DRUG_FORMULARY).insert(data).execute()
    invalidate_cache_tags(*_CACHE_TAGS)
    return result.data[0] if result.data else data


# ─────────────────────────────────────────────────────────────────────────────
# Batches (FEFO)
# ─────────────────────────────────────────────────────────────────────────────

def list_live_batches(formulary_id: int) -> List[Dict[str, Any]]:
    """Batches that can actually be dispensed today.

    FEFO order: earliest-expiring first (NULL expiry sorts last), then
    earliest-received for ties.

    Expired batches are excluded, not merely sorted last. "Live" has to mean
    dispensable or the word is misleading: an expired batch must never appear
    in a picker where a pharmacist could hand it to a patient. They remain in
    the table for reference and are reachable through list_expired_batches.
    """
    return _q(
        f"""SELECT * FROM public.{TABLE_INVENTORY_BATCHES}
            WHERE formulary_id = %s
              AND quantity_on_hand > 0
              AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE)
            ORDER BY expiry_date ASC NULLS LAST, received_at ASC, id ASC""",
        (formulary_id,),
    )


def list_all_batches(formulary_id: int) -> List[Dict[str, Any]]:
    return _q(
        f"""SELECT * FROM public.{TABLE_INVENTORY_BATCHES}
            WHERE formulary_id = %s
            ORDER BY expiry_date ASC NULLS LAST, received_at ASC, id ASC""",
        (formulary_id,),
    )


def upsert_batch(
    formulary_id: int,
    batch_number: str,
    quantity_received: float,
    unit_cost: Optional[float] = None,
    supplier: Optional[str] = None,
    location: Optional[str] = None,
    expiry_date: Optional[str] = None,
    notes: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Receive stock. Re-receiving the same batch number tops up the
    existing row (real pharmacy practice) instead of creating a duplicate."""
    existing_resp = (
        db.table(TABLE_INVENTORY_BATCHES).select("*")
        .eq("formulary_id", formulary_id).ilike("batch_number", batch_number).limit(1).execute()
    )
    if existing_resp.data:
        row = existing_resp.data[0]
        updates: Dict[str, Any] = {
            "quantity_on_hand": float(row.get("quantity_on_hand") or 0) + float(quantity_received),
            "quantity_received": float(row.get("quantity_received") or 0) + float(quantity_received),
            "updated_at": _now_iso(),
        }
        if unit_cost is not None:
            updates["unit_cost"] = unit_cost
        if supplier:
            updates["supplier"] = supplier
        if location:
            updates["location"] = location
        if expiry_date:
            updates["expiry_date"] = expiry_date
        if notes:
            updates["notes"] = notes
        db.table(TABLE_INVENTORY_BATCHES).update(updates).eq("id", row["id"]).execute()
        invalidate_cache_tags(*_CACHE_TAGS)
        _close_stock_order(formulary_id, quantity_received, batch_number)
        return {**row, **updates}

    data = {
        "formulary_id": formulary_id,
        "batch_number": batch_number,
        "quantity_on_hand": quantity_received,
        "quantity_received": quantity_received,
        "unit_cost": unit_cost or 0,
        "supplier": supplier,
        "location": location,
        "expiry_date": expiry_date,
        "notes": notes,
        "created_by": created_by,
    }
    result = db.table(TABLE_INVENTORY_BATCHES).insert(data).execute()
    invalidate_cache_tags(*_CACHE_TAGS)
    _close_stock_order(formulary_id, quantity_received, batch_number)
    return result.data[0] if result.data else data


def _close_stock_order(formulary_id: int, quantity: float, batch_number: str) -> None:
    """Stock arrived on the shelf: its open stock order is received (services/stock_orders.receive_for)."""
    try:
        from src.fin.db import tx
        from src.services.stock_orders import receive_for
        with tx() as conn:
            receive_for(conn, formulary_id, float(quantity or 0), "pharmacy_receipt", batch_number)
    except Exception as exc:
        logger.warning("stock order not closed for formulary %s after receipt: %s", formulary_id, exc)


def adjust_batch(batch_id: int, adjustment: float, reason: str = "manual_adjustment") -> Dict[str, Any]:
    batch = _q1(f"SELECT * FROM public.{TABLE_INVENTORY_BATCHES} WHERE id = %s", (batch_id,))
    if not batch:
        raise ValueError(f"Batch {batch_id} not found")
    current = float(batch.get("quantity_on_hand") or 0)
    new_qty = max(0.0, current + adjustment)
    db.table(TABLE_INVENTORY_BATCHES).update({"quantity_on_hand": new_qty, "updated_at": _now_iso()}).eq("id", batch_id).execute()
    invalidate_cache_tags(*_CACHE_TAGS)
    return {"batch_id": batch_id, "batch_number": batch.get("batch_number"), "previous_qty": current, "new_qty": new_qty, "reason": reason}


def apply_fefo_deduction(formulary_id: int, quantity: float, batch_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Best-effort FEFO deduction — never blocks the clinical dispense action
    on inventory bookkeeping. Deducts what's recorded as available and stops
    (mirrors the old flat model's floor-at-zero: this table is a tracking
    aid, not a hard gate on dispensing a prescribed drug). Returns the
    batches actually touched; caller can compare the sum of quantity_taken
    against the requested quantity to detect a shortfall."""
    if batch_id:
        one = _q1(f"SELECT * FROM public.{TABLE_INVENTORY_BATCHES} WHERE id = %s AND formulary_id = %s", (batch_id, formulary_id))
        batches = [one] if one else []
    else:
        batches = list_live_batches(formulary_id)

    remaining = quantity
    taken: List[Dict[str, Any]] = []
    for b in batches:
        if remaining <= 0:
            break
        on_hand = float(b.get("quantity_on_hand") or 0)
        if on_hand <= 0:
            continue
        take = min(remaining, on_hand)
        db.table(TABLE_INVENTORY_BATCHES).update(
            {"quantity_on_hand": on_hand - take, "updated_at": _now_iso()}
        ).eq("id", b["id"]).execute()
        taken.append({
            "batch_id": b["id"], "batch_number": b.get("batch_number"),
            "expiry_date": b.get("expiry_date"), "quantity_taken": take,
        })
        remaining -= take
    if taken:
        invalidate_cache_tags(*_CACHE_TAGS)
    return taken


# ─────────────────────────────────────────────────────────────────────────────
# Demand velocity + risk tiers
# ─────────────────────────────────────────────────────────────────────────────

def _demand_counts_by_name(window_days: int = PHARMACY_DEMAND_WINDOW_DAYS) -> Dict[str, tuple]:
    """One aggregate query covering every drug at once, keyed by
    lower(drug_name) -> (current_window_cnt, prior_window_cnt).

    Replaces calling compute_demand_velocity() per drug -- that was 2
    unindexed OR-chain queries against royan_prescriptions PER CARD, so the
    uncached 536-drug catalog (workspace summary, or any filtered card
    query, which must scan the full set to filter correctly -- see
    list_drug_cards) cost ~1,072 sequential-scan round trips, measured at
    ~18s. Real prescribing activity is currently near-zero (see docstring
    below), so nearly all of that cost was wasted work recomputing
    "no_recent_demand" over and over.
    """
    rows = _q(f"""
        SELECT lower(drug_name) AS name,
               COUNT(*) FILTER (WHERE prescribed_at >= now() - (%s || ' days')::interval) AS current_cnt,
               COUNT(*) FILTER (
                   WHERE prescribed_at >= now() - (%s || ' days')::interval
                     AND prescribed_at <  now() - (%s || ' days')::interval
               ) AS prior_cnt
        FROM public.{TABLE_PRESCRIPTIONS}
        WHERE external_source IS NULL
        GROUP BY lower(drug_name)
    """, (window_days, window_days * 2, window_days))
    return {r["name"]: (int(r["current_cnt"] or 0), int(r["prior_cnt"] or 0)) for r in rows}


def _velocity_from_window_counts(current_qty: int, prior_qty: int, window_days: int) -> Dict[str, Any]:
    if current_qty == 0 and prior_qty == 0:
        return {"avg_daily_demand": 0.0, "current_window_qty": 0, "prior_window_qty": 0,
                "direction": "stable", "confidence": "no_recent_demand"}

    avg_daily = current_qty / float(window_days)
    if prior_qty == 0:
        direction = "rising" if current_qty > 0 else "stable"
    else:
        delta = (current_qty - prior_qty) / float(prior_qty)
        direction = "rising" if delta > 0.15 else "falling" if delta < -0.15 else "stable"

    return {"avg_daily_demand": round(avg_daily, 3), "current_window_qty": current_qty,
            "prior_window_qty": prior_qty, "direction": direction, "confidence": "estimated"}


def compute_demand_velocity(
    drug_names: List[str],
    window_days: int = PHARMACY_DEMAND_WINDOW_DAYS,
    counts_by_name: Optional[Dict[str, tuple]] = None,
) -> Dict[str, Any]:
    """Demand signal from royan_prescriptions (excludes Hope-import
    placeholder rows, same convention as pharmacy_dispensing.py's own
    list_prescriptions). Real usage in this system is currently near-zero,
    so this must degrade to an explicit no-data state, never a fabricated
    number.

    Pass counts_by_name (from _demand_counts_by_name(), one query for the
    whole catalog) when computing this for many drugs in a loop -- avoids
    2 fresh queries per drug. Single-drug callers (e.g. get_drug_detail)
    can omit it and this queries directly as before.
    """
    names = [n.strip() for n in (drug_names or []) if n and n.strip()]
    if not names:
        return {"avg_daily_demand": 0.0, "current_window_qty": 0, "prior_window_qty": 0,
                "direction": "stable", "confidence": "no_recent_demand"}

    if counts_by_name is not None:
        current_qty = sum(counts_by_name.get(n.lower(), (0, 0))[0] for n in names)
        prior_qty = sum(counts_by_name.get(n.lower(), (0, 0))[1] for n in names)
        return _velocity_from_window_counts(current_qty, prior_qty, window_days)

    match_clause = " OR ".join(["lower(drug_name) = lower(%s)"] * len(names))
    name_params = tuple(names)

    current = _q1(
        f"""SELECT COUNT(*) AS cnt FROM public.{TABLE_PRESCRIPTIONS}
            WHERE external_source IS NULL AND ({match_clause})
              AND prescribed_at >= now() - (%s || ' days')::interval""",
        name_params + (window_days,),
    ) or {}
    prior = _q1(
        f"""SELECT COUNT(*) AS cnt FROM public.{TABLE_PRESCRIPTIONS}
            WHERE external_source IS NULL AND ({match_clause})
              AND prescribed_at >= now() - (%s || ' days')::interval
              AND prescribed_at <  now() - (%s || ' days')::interval""",
        name_params + (window_days * 2, window_days),
    ) or {}

    current_qty = int(current.get("cnt") or 0)
    prior_qty = int(prior.get("cnt") or 0)
    return _velocity_from_window_counts(current_qty, prior_qty, window_days)


def _expiry_tier_floor(nearest_expiry: Optional[Any]) -> Optional[str]:
    """Expired or expiring-within-window stock is a real risk even when the
    stock-coverage math looks fine -- ample quantity that expires in two
    weeks still needs attention now. Returns the tier this alone floors the
    drug at, or None if expiry isn't a concern (used as a floor, never a
    downgrade, by the caller)."""
    if not nearest_expiry:
        return None
    expiry_date = nearest_expiry if isinstance(nearest_expiry, dt.date) else dt.date.fromisoformat(str(nearest_expiry)[:10])
    days_to_expiry = (expiry_date - dt.date.today()).days
    if days_to_expiry <= PHARMACY_EXPIRING_SOON_DAYS:
        return "WARNING"
    return None


def compute_risk_tier(
    qty_on_hand: float,
    avg_daily_demand: float,
    lead_time_days: Optional[int],
    safety_stock_days: Optional[int],
    reorder_level: Optional[float],
    nearest_expiry: Optional[Any] = None,
) -> Dict[str, Any]:
    lead_time = lead_time_days or PHARMACY_DEFAULT_LEAD_TIME_DAYS
    safety = safety_stock_days or PHARMACY_DEFAULT_SAFETY_STOCK_DAYS
    review = PHARMACY_REVIEW_CYCLE_DAYS
    reorder_floor = float(reorder_level or 0)

    stock_coverage_days: Optional[float] = None
    predicted_stockout_date: Optional[str] = None

    if qty_on_hand <= 0:
        tier = "CRITICAL"
    elif avg_daily_demand <= 0:
        tier = "CRITICAL" if qty_on_hand <= reorder_floor else "MONITOR"
    else:
        stock_coverage_days = qty_on_hand / avg_daily_demand
        if stock_coverage_days < lead_time:
            tier = "CRITICAL"
        elif stock_coverage_days < lead_time + safety:
            tier = "WARNING"
        elif stock_coverage_days < lead_time + safety + review:
            tier = "MONITOR"
        else:
            tier = "ADEQUATE"
        predicted_stockout_date = (dt.date.today() + dt.timedelta(days=int(stock_coverage_days))).isoformat()

    expiry_floor = _expiry_tier_floor(nearest_expiry)
    if expiry_floor and _TIER_ORDER[expiry_floor] < _TIER_ORDER[tier]:
        tier = expiry_floor

    recommended_reorder_qty: Optional[float] = None
    if tier != "ADEQUATE":
        if avg_daily_demand > 0:
            recommended_reorder_qty = max(0.0, round(avg_daily_demand * (lead_time + safety) - qty_on_hand))
        else:
            recommended_reorder_qty = max(0.0, round(reorder_floor * 2 - qty_on_hand))

    return {
        "tier": tier,
        "stock_coverage_days": round(stock_coverage_days, 1) if stock_coverage_days is not None else None,
        "recommended_reorder_qty": recommended_reorder_qty,
        "predicted_stockout_date": predicted_stockout_date,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cards / drill-down / workspace summary
# ─────────────────────────────────────────────────────────────────────────────

def _formulary_names(f: Dict[str, Any]) -> List[str]:
    return [n for n in [f.get("generic_name"), f.get("brand_name"), f.get("code")] if n]


@ttl_cache(ttl_seconds=30, tags=_CACHE_TAGS)
def list_drug_cards(
    category: Optional[str] = None,
    risk_tier: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Grouped-by-drug, live-stock-only cards (a drug with N concurrently
    in-stock batches is one card, not N).

    Each card runs compute_demand_velocity() below, which is 2 DB round-trips
    on its own — with the catalog now at 800+ SKUs (and growing), building
    every card unconditionally made this endpoint scale linearly with catalog
    size. When `limit` is given, the cap is applied here at the SQL level,
    ordered by most-recently-dispensed first, so the expensive per-card work
    below only ever runs for the page actually being shown — not the whole
    catalog. get_workspace_summary() still calls this with no limit since its
    tier counts/total_skus need the full set.
    """
    # category/risk_tier/search are only knowable after the per-card Python
    # work below (risk_tier depends on demand velocity, computed per drug) --
    # capping at the SQL layer before that would silently drop real matches
    # that just aren't among the N most-recently-dispensed drugs. So the SQL
    # cap only applies to the true default (unfiltered) view; a filtered
    # query computes the full set and paginates in Python instead.
    filtering = bool(category or risk_tier or search)
    order_and_limit = ""
    params: tuple = ()
    if limit is not None and not filtering:
        order_and_limit = "ORDER BY last_dispensed_at DESC NULLS LAST LIMIT %s OFFSET %s"
        params = (limit, offset)

    # last_dispensed_at is pre-aggregated to one row per formulary_id before
    # joining -- joining royan_dispensing directly here would fan out the
    # batch aggregates (SUM/COUNT) across every historical dispensing row
    # for that drug, since formulary_id is a real 1:N link, not 1:1.
    agg_rows = _q(f"""
        SELECT b.formulary_id,
               SUM(b.quantity_on_hand) AS total_qty,
               COUNT(*) AS batch_count,
               MIN(b.expiry_date) AS nearest_expiry,
               SUM(b.quantity_on_hand * b.unit_cost) AS stock_value,
               MAX(dd.last_dispensed_at) AS last_dispensed_at
        FROM public.{TABLE_INVENTORY_BATCHES} b
        LEFT JOIN (
            SELECT formulary_id, MAX(dispensed_at) AS last_dispensed_at
            FROM public.{TABLE_DISPENSING}
            WHERE formulary_id IS NOT NULL
            GROUP BY formulary_id
        ) dd ON dd.formulary_id = b.formulary_id
        WHERE b.quantity_on_hand > 0
        GROUP BY b.formulary_id
        {order_and_limit}
    """, params)
    if not agg_rows:
        return []

    formulary_ids = [r["formulary_id"] for r in agg_rows]
    placeholders = ",".join(["%s"] * len(formulary_ids))
    formulary_rows = _q(f"SELECT * FROM public.{TABLE_DRUG_FORMULARY} WHERE id IN ({placeholders})", tuple(formulary_ids))
    formulary_map = {f["id"]: f for f in formulary_rows}

    search_lower = search.strip().lower() if search else None
    # One query for every drug's demand counts instead of 2 per card -- see
    # _demand_counts_by_name's docstring for why this matters here.
    counts_by_name = _demand_counts_by_name()
    cards: List[Dict[str, Any]] = []
    for agg in agg_rows:
        f = formulary_map.get(agg["formulary_id"])
        if not f:
            continue
        if category and f.get("category") != category:
            continue
        if search_lower and search_lower not in (f.get("generic_name") or "").lower() and search_lower not in (f.get("brand_name") or "").lower():
            continue

        demand = compute_demand_velocity(_formulary_names(f), counts_by_name=counts_by_name)
        total_qty = float(agg["total_qty"] or 0)
        risk = compute_risk_tier(total_qty, demand["avg_daily_demand"], f.get("lead_time_days"), f.get("safety_stock_days"), f.get("reorder_level"), agg.get("nearest_expiry"))
        if risk_tier and risk["tier"] != risk_tier:
            continue

        cards.append({
            "formulary_id": f["id"],
            "drug_name": f.get("generic_name") or f.get("brand_name") or f.get("code"),
            "brand_name": f.get("brand_name"),
            "category": f.get("category"),
            "form": f.get("form"),
            "strength": f.get("strength"),
            "total_qty_on_hand": total_qty,
            "batch_count": int(agg["batch_count"] or 0),
            "nearest_expiry": agg["nearest_expiry"].isoformat() if agg.get("nearest_expiry") else None,
            "stock_value": round(float(agg["stock_value"] or 0), 2),
            "risk_tier": risk["tier"],
            "stock_coverage_days": risk["stock_coverage_days"],
            "recommended_reorder_qty": risk["recommended_reorder_qty"],
            "predicted_stockout_date": risk["predicted_stockout_date"],
            "demand_confidence": demand["confidence"],
            "demand_direction": demand["direction"],
        })

    cards.sort(key=lambda c: (_TIER_ORDER.get(c["risk_tier"], 9), c["drug_name"] or ""))
    if filtering and limit is not None:
        cards = cards[offset:offset + limit]
    return cards


@ttl_cache(ttl_seconds=30, tags=_CACHE_TAGS)
def get_drug_detail(formulary_id: int) -> Optional[Dict[str, Any]]:
    formulary = _q1(f"SELECT * FROM public.{TABLE_DRUG_FORMULARY} WHERE id = %s", (formulary_id,))
    if not formulary:
        return None
    # Only what is on the shelf. This panel previously listed every batch ever
    # recorded -- 263 rows for ACT DS, all expired with nothing in them -- which
    # buried the one batch that actually holds stock.
    batches = list_live_batches(formulary_id)
    historical_batches = [
        b for b in list_all_batches(formulary_id)
        if float(b.get("quantity_on_hand") or 0) <= 0
        or (b.get("expiry_date") and str(b["expiry_date"]) < _dt.date.today().isoformat())
    ]
    recent_dispensing = _q(
        f"""SELECT * FROM public.{TABLE_DISPENSING} WHERE formulary_id = %s
            ORDER BY dispensed_at DESC LIMIT 20""",
        (formulary_id,),
    )
    demand = compute_demand_velocity(_formulary_names(formulary))
    total_qty = sum(float(b.get("quantity_on_hand") or 0) for b in batches)
    live_expiries = [b.get("expiry_date") for b in batches if float(b.get("quantity_on_hand") or 0) > 0 and b.get("expiry_date")]
    nearest_expiry = min(live_expiries) if live_expiries else None
    risk = compute_risk_tier(total_qty, demand["avg_daily_demand"], formulary.get("lead_time_days"), formulary.get("safety_stock_days"), formulary.get("reorder_level"), nearest_expiry)
    return {
        "formulary": formulary,
        "batches": batches,
        # Kept out of the main list but still reachable: history, not stock.
        "historical_batches": historical_batches[:100],
        "historical_batch_count": len(historical_batches),
        "recent_dispensing": recent_dispensing,
        "demand": demand,
        "risk": risk,
        "total_qty_on_hand": total_qty,
    }


@ttl_cache(ttl_seconds=30, tags=_CACHE_TAGS)
def get_workspace_summary() -> Dict[str, Any]:
    cards = list_drug_cards()
    tier_counts = {t: 0 for t in ("CRITICAL", "WARNING", "MONITOR", "ADEQUATE")}
    for c in cards:
        tier_counts[c["risk_tier"]] = tier_counts.get(c["risk_tier"], 0) + 1

    today = dt.date.today()
    cutoff = (today + dt.timedelta(days=PHARMACY_EXPIRING_SOON_DAYS)).isoformat()
    expiring = _q1(
        f"""SELECT COUNT(DISTINCT formulary_id) AS cnt FROM public.{TABLE_INVENTORY_BATCHES}
            WHERE quantity_on_hand > 0 AND expiry_date IS NOT NULL
              AND expiry_date >= %s AND expiry_date <= %s""",
        (today.isoformat(), cutoff),
    ) or {}
    expired = _q1(
        f"""SELECT COUNT(DISTINCT formulary_id) AS cnt FROM public.{TABLE_INVENTORY_BATCHES}
            WHERE quantity_on_hand > 0 AND expiry_date IS NOT NULL AND expiry_date < %s""",
        (today.isoformat(),),
    ) or {}
    pending = _q1(
        f"""SELECT COUNT(*) AS cnt FROM public.{TABLE_REPLENISHMENT_REQUESTS}
            WHERE status IN ('recommended', 'approved', 'ordered')"""
    ) or {}

    return {
        "total_skus": len(cards),
        "stock_value": round(sum(c["stock_value"] for c in cards), 2),
        "tier_counts": tier_counts,
        "expiring_soon_count": int(expiring.get("cnt") or 0),
        "expired_in_stock_count": int(expired.get("cnt") or 0),
        "pending_replenishment_count": int(pending.get("cnt") or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Trends
# ─────────────────────────────────────────────────────────────────────────────

def most_prescribed(window_days: int = PHARMACY_DEMAND_WINDOW_DAYS, limit: int = 10) -> List[Dict[str, Any]]:
    return _q(
        f"""SELECT drug_name, COUNT(*) AS rx_count, COALESCE(SUM(quantity), 0) AS total_qty
            FROM public.{TABLE_PRESCRIPTIONS}
            WHERE external_source IS NULL AND prescribed_at >= now() - (%s || ' days')::interval
            GROUP BY drug_name
            ORDER BY rx_count DESC
            LIMIT %s""",
        (window_days, limit),
    )


def recently_dispensed(limit: int = 20) -> List[Dict[str, Any]]:
    return _q(
        f"""SELECT id, drug_name, quantity_dispensed, unit, batch_number, expiry_date,
                   dispensed_by, dispensed_at, patient_id
            FROM public.{TABLE_DISPENSING}
            ORDER BY dispensed_at DESC
            LIMIT %s""",
        (limit,),
    )
