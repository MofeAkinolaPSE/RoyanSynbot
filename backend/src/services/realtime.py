"""Live updates over WebSockets, across every worker process.

Each worker holds the sockets of the browsers connected to it. A broadcast is delivered to this
worker's sockets at once and published on Redis; every other worker receives it from Redis and
delivers it to its own sockets. Without Redis (or before it connects) delivery is local only, which
is exactly the single-process behaviour.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)
_REDIS_CHANNEL = "royan:realtime"


class RealtimeHub:
    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._origin = uuid.uuid4().hex          # this worker; its own messages are not delivered twice
        self._redis = None
        self._listener: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._channels[channel].add(websocket)

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._channels.get(channel)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._channels.pop(channel, None)

    async def broadcast(self, channel: str, payload: dict[str, Any]) -> None:
        await self._deliver(channel, payload)
        if self._redis is not None:
            try:
                await self._redis.publish(_REDIS_CHANNEL, json.dumps({"o": self._origin, "c": channel, "p": payload}, default=str))
            except Exception as exc:
                log.warning("realtime publish failed (local delivery only): %s", exc)

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget broadcast from anywhere: an async handler or a plain `def` handler running
        in the thread pool. Never blocks and never raises."""
        try:
            asyncio.get_running_loop().create_task(self.broadcast(channel, payload))
            return
        except RuntimeError:
            pass
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(channel, payload), self._loop)

    async def _deliver(self, channel: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._channels.get(channel, set()))
        if not sockets:
            return

        failed: list[WebSocket] = []
        message = json.dumps(payload, default=str)
        for socket in sockets:
            try:
                await socket.send_text(message)
            except Exception:
                failed.append(socket)

        if failed:
            async with self._lock:
                conns = self._channels.get(channel)
                if not conns:
                    return
                for socket in failed:
                    conns.discard(socket)
                if not conns:
                    self._channels.pop(channel, None)

    async def start_fanout(self) -> None:
        """Called once per worker at startup: subscribe to the other workers' broadcasts."""
        self._loop = asyncio.get_running_loop()
        url = os.getenv("REDIS_URL")
        if not url or self._listener is not None:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(url, decode_responses=True)
            await self._redis.ping()
        except Exception as exc:
            log.warning("realtime fan-out unavailable, single-worker delivery only: %s", exc)
            self._redis = None
            return
        self._listener = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(_REDIS_CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        data = json.loads(msg["data"])
                    except Exception:
                        continue
                    if data.get("o") != self._origin:
                        await self._deliver(data.get("c"), data.get("p") or {})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("realtime fan-out listener restarting: %s", exc)
                await asyncio.sleep(2)


realtime_hub = RealtimeHub()
