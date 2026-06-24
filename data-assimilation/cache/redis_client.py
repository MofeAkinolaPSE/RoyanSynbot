"""Optional Redis cache warmer for active queue state.

Only active when REDIS_URL is set in the environment.
Warms per-department active encounter counts after each pipeline run.

Key pattern: royan:queue:{department}:active_count
TTL: 300 seconds (5 minutes)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_REDIS_TTL = 300  # 5 minutes — matches the Anthropic prompt cache TTL heuristic


class QueueCache:
    def __init__(self, redis_url: str):
        try:
            import redis as redis_lib
            self._client = redis_lib.from_url(redis_url, decode_responses=True)
            self._client.ping()
            self._available = True
            logger.info("Redis connected: %s", redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — cache warming disabled", exc)
            self._client = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def warm_active_queue(self, conn) -> int:
        """Query active encounter counts per department and write to Redis.

        Returns number of cache keys written.
        """
        if not self._available or self._client is None:
            return 0

        written = 0
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COALESCE(department, 'Unknown') AS department,
                        COUNT(*) AS active_count
                    FROM public.royan_encounters
                    WHERE status NOT IN ('discharged')
                    GROUP BY COALESCE(department, 'Unknown')
                """)
                rows = cur.fetchall()

            pipe = self._client.pipeline()
            for dept, count in rows:
                key = f"royan:queue:{dept}:active_count"
                pipe.set(key, count, ex=_REDIS_TTL)
                written += 1
            pipe.execute()
            logger.info("Redis cache warmed: %d department keys (TTL %ds)", written, _REDIS_TTL)
        except Exception as exc:
            logger.warning("Redis cache warm failed: %s", exc)
        return written

    def invalidate_entity(self, entity: str) -> None:
        """Delete all Redis keys related to an entity (e.g. after a load)."""
        if not self._available or self._client is None:
            return
        try:
            pattern = f"royan:{entity}:*"
            keys = self._client.keys(pattern)
            if keys:
                self._client.delete(*keys)
                logger.debug("Redis: invalidated %d keys for entity '%s'", len(keys), entity)
        except Exception as exc:
            logger.warning("Redis invalidation failed for '%s': %s", entity, exc)

    def set_run_id(self, run_id: str) -> None:
        """Store the last successful run_id for dashboard polling."""
        if not self._available or self._client is None:
            return
        try:
            self._client.set("royan:pipeline:last_run_id", run_id, ex=86400)  # 24h
        except Exception:
            pass


def get_queue_cache(redis_url: Optional[str]) -> Optional[QueueCache]:
    """Factory — returns None if redis_url is falsy."""
    if not redis_url:
        return None
    return QueueCache(redis_url)
