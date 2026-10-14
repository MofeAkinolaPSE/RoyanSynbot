from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Hashable, Iterable, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis client — lazily initialised, optional
# ---------------------------------------------------------------------------

_redis_client = None
_redis_available: bool | None = None   # None = not yet probed
_redis_init_lock = threading.Lock()


def _get_redis():
    """Return a live Redis client, or None if Redis is unavailable."""
    global _redis_client, _redis_available
    if _redis_available is False:
        return None
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        url = os.getenv("REDIS_URL", "").strip()
        if not url:
            _redis_available = False
            return None
        try:
            import redis as _redis_lib  # imported lazily so the package is optional
            client = _redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=2)
            client.ping()
            _redis_client = client
            _redis_available = True
            logger.info("Redis cache connected: %s", url)
        except Exception as exc:
            _redis_available = False
            logger.warning("Redis unavailable (%s); falling back to in-process cache", exc)
            return None
    return _redis_client


def get_redis_client():
    """Public accessor for other modules that need a raw shared Redis client
    (e.g. one-time WS tickets) rather than the ttl_cache decorator."""
    return _get_redis()


def _redis_key(raw: Hashable) -> str:
    digest = hashlib.sha256(
        json.dumps(raw, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"ttl:{digest}"


def _redis_get(rkey: str) -> Any:
    r = _get_redis()
    if r is None:
        return None
    try:
        val = r.get(rkey)
        return json.loads(val) if val is not None else None
    except Exception:
        return None


def _redis_set(rkey: str, value: Any, ttl_seconds: int, tags: Iterable[str] | None) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(rkey, ttl_seconds, json.dumps(value, default=str))
        if tags:
            pipe = r.pipeline(transaction=False)
            for tag in tags:
                tkey = f"tag:{tag}"
                pipe.sadd(tkey, rkey)
                pipe.expire(tkey, ttl_seconds + 120)
            pipe.execute()
    except Exception:
        pass


def _redis_invalidate(tags: Iterable[str]) -> int:
    r = _get_redis()
    if r is None:
        return 0
    removed = 0
    try:
        for tag in tags:
            tkey = f"tag:{tag}"
            keys = r.smembers(tkey)
            if keys:
                r.delete(*keys)
                removed += len(keys)
            r.delete(tkey)
    except Exception:
        pass
    return removed


# ---------------------------------------------------------------------------
# In-process fallback cache (used when Redis is unavailable)
# ---------------------------------------------------------------------------

class _TTLCache:
    """Simple in-process TTL cache for computed aggregates.

    Used as the fallback when Redis is not configured. For multiple workers
    each process keeps its own cache; use Redis (REDIS_URL env var) for a
    shared cache that works correctly across Swarm replicas.
    """

    def __init__(self) -> None:
        self._store: Dict[Hashable, Tuple[float, Any]] = {}
        self._tag_index: Dict[str, set[Hashable]] = {}
        self._lock = threading.RLock()

    def get(self, key: Hashable) -> Any | None:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at < now:
                self._store.pop(key, None)
                self._remove_key_from_tags(key)
                return None
            return value

    def set(self, key: Hashable, value: Any, ttl_seconds: int, tags: Iterable[str] | None = None) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[key] = (expires_at, value)
            if tags:
                for tag in tags:
                    normalized = (tag or "").strip()
                    if not normalized:
                        continue
                    self._tag_index.setdefault(normalized, set()).add(key)

    def invalidate_tags(self, tags: Iterable[str]) -> int:
        removed = 0
        with self._lock:
            for tag in tags:
                normalized = (tag or "").strip()
                if not normalized:
                    continue
                keys = list(self._tag_index.get(normalized, set()))
                for key in keys:
                    if key in self._store:
                        self._store.pop(key, None)
                        removed += 1
                    self._remove_key_from_tags(key)
                self._tag_index.pop(normalized, None)
        return removed

    def _remove_key_from_tags(self, key: Hashable) -> None:
        empty_tags: list[str] = []
        for tag, keys in self._tag_index.items():
            if key in keys:
                keys.discard(key)
            if not keys:
                empty_tags.append(tag)
        for tag in empty_tags:
            self._tag_index.pop(tag, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._tag_index.clear()


_global_cache = _TTLCache()


# ---------------------------------------------------------------------------
# Cache key builder
# ---------------------------------------------------------------------------

def _make_key(
    func_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    ignore_kwargs: Iterable[str],
) -> Hashable:
    filtered_kwargs = {k: v for k, v in kwargs.items() if k not in set(ignore_kwargs)}
    return (
        func_name,
        args,
        tuple(sorted(filtered_kwargs.items(), key=lambda item: item[0])),
    )


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------

def ttl_cache(
    ttl_seconds: int,
    ignore_kwargs: Iterable[str] | None = None,
    tags: Iterable[str] | Callable[..., Iterable[str]] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Cache function results for a fixed TTL.

    Uses Redis when REDIS_URL is set (shared across all Swarm replicas).
    Falls back to in-process cache otherwise (single-replica safe).

    `tags` may be a static iterable of tag strings, or a callable receiving
    the wrapped call's (*args, **kwargs) and returning the tags for that
    specific call — enabling per-entity invalidation, e.g.:

        @ttl_cache(300, tags=lambda patient_id, **kw: [f"patient:{patient_id}"])
        def get_patient_context(patient_id): ...

        invalidate_cache_tags(f"patient:{patient_id}")  # after any write
    """
    if ignore_kwargs is None:
        ignore_kwargs = []

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            raw_key = _make_key(func.__name__, args, kwargs, ignore_kwargs)
            resolved_tags = tags(*args, **kwargs) if callable(tags) else tags

            if _get_redis() is not None:
                rkey = _redis_key(raw_key)
                cached = _redis_get(rkey)
                if cached is not None:
                    return cached
                value = func(*args, **kwargs)
                _redis_set(rkey, value, ttl_seconds, resolved_tags)
                return value

            # In-process fallback
            cached = _global_cache.get(raw_key)
            if cached is not None:
                return cached
            value = func(*args, **kwargs)
            _global_cache.set(raw_key, value, ttl_seconds, tags=resolved_tags)
            return value

        return wrapper

    return decorator


def invalidate_cache_tags(*tags: str) -> int:
    redis_removed = _redis_invalidate(tags)
    local_removed = _global_cache.invalidate_tags(tags)
    return redis_removed + local_removed


def clear_cache() -> None:
    _global_cache.clear()
    r = _get_redis()
    if r:
        try:
            for key in r.scan_iter("ttl:*"):
                r.delete(key)
            for key in r.scan_iter("tag:*"):
                r.delete(key)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Shared endpoint responses (one rebuild across every worker)
# ---------------------------------------------------------------------------

def shared_response(key: str, ttl_seconds: int, build: Callable[[], Any], refresh: bool = False) -> Any:
    """An endpoint's response, built once and shared by every worker process through Redis.

    For the heavy read-only dashboards (executive overview, payer directory, reorder plan): with several
    workers each holding its own cache, an expiry made every worker run the same multi-second aggregate
    at once. Here the first worker to miss takes a short Redis lock and builds; the others wait for its
    result instead of repeating the query. The value is stored exactly as FastAPI would serialise it
    (jsonable_encoder), so a cached response is identical to a fresh one. Without Redis it simply builds.
    """
    from fastapi.encoders import jsonable_encoder
    r = _get_redis()
    if r is None:
        return jsonable_encoder(build())
    rkey, lkey = f"resp:{key}", f"resp:{key}:lock"
    if not refresh:
        try:
            hit = r.get(rkey)
            if hit is not None:
                return json.loads(hit)
        except Exception:
            pass
    try:
        mine = bool(r.set(lkey, "1", nx=True, ex=60))
    except Exception:
        mine = True
    if not mine and not refresh:
        deadline = time.monotonic() + 20          # another worker is building it: wait for that result
        while time.monotonic() < deadline:
            time.sleep(0.15)
            try:
                hit = r.get(rkey)
                if hit is not None:
                    return json.loads(hit)
                if not r.exists(lkey):
                    break
            except Exception:
                break
    try:
        value = jsonable_encoder(build())
        try:
            r.set(rkey, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:
            logger.warning("shared_response: could not store %s: %s", key, exc)
        return value
    finally:
        if mine:
            try:
                r.delete(lkey)
            except Exception:
                pass


def drop_shared_response(*keys: str) -> None:
    """Forget cached responses after a write that changes them."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(*(f"resp:{k}" for k in keys))
    except Exception:
        pass
