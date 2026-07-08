#!/usr/bin/env python3
"""Log-tail watcher sidecar.

Watches docker logs for the backend/nginx/db containers, normalizes and
fingerprints recurring errors (PHI-scrubbed), and posts them to the backend's
internal signal-ingestion endpoint so they flow into the existing
capability-discovery proposal queue instead of a separate, parallel system.

This is the primary detection layer for this codebase specifically: the
shared DB-query helper (backend/src/local_db.py) only re-raises exceptions
for insert/update/upsert actions — select failures (missing tables/columns,
the majority of real bugs found in this app) are caught and only logged, so
they never reach a Python-exception-based tracker. Matching the literal log
line format here is what actually catches them.

Does not mount the Docker socket directly — talks to a docker-socket-proxy
(tecnativa/docker-socket-proxy) that only allows read-only container/log/
event operations (CONTAINERS, LOGS, EVENTS; POST=0 blocks every mutating
call). See deploy/docker-compose.yml for the isolated network topology.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Optional

import docker
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("log_watcher")

DOCKER_PROXY_URL = os.environ.get("DOCKER_PROXY_URL", "tcp://docker-socket-proxy:2375")
BACKEND_INTERNAL_URL = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")
INTERNAL_SIGNAL_KEY = os.environ.get("INTERNAL_SIGNAL_KEY", "")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))

WATCHED_CONTAINERS = {"royan_backend", "royan_nginx", "royan_db"}

# Container name -> [(pattern, severity), ...]. First match wins per line.
PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {
    "royan_backend": [
        (re.compile(r"local_db TableQuery execute error on "), "medium"),
    ],
    "royan_nginx": [
        (re.compile(r"no live upstreams"), "high"),
        (re.compile(r"could not be resolved"), "high"),
        (re.compile(r"upstream timed out"), "medium"),
        (re.compile(r"connect\(\) failed"), "medium"),
        (re.compile(r"SSL_do_handshake\(\) failed"), "low"),
    ],
    "royan_db": [
        (re.compile(r"\bPANIC:  "), "critical"),
        (re.compile(r"\bFATAL:  "), "high"),
        (re.compile(r"\bERROR:  "), "medium"),
    ],
}

TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):")
FILE_LINE_RE = re.compile(r'File "([^"]+)", line (\d+)')

# ---------------------------------------------------------------------------
# Normalization / fingerprinting — required both for correct dedup
# (record_signal upserts on exact signal_type+description match) and for PHI
# safety: Postgres/psycopg2 error text quotes the actual failing value
# (e.g. "Key (mrn)=(...) already exists"), so raw error text must never flow
# untouched into royan_capability_signals.description.
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
_QUOTED_SINGLE_RE = re.compile(r"'[^']*'")
_QUOTED_DOUBLE_RE = re.compile(r'"[^"]*"')
_LONG_NUM_RE = re.compile(r"\b\d{3,}\b")


def normalize(text: str) -> str:
    text = _UUID_RE.sub("<uuid>", text)
    text = _TS_RE.sub("<ts>", text)
    text = _QUOTED_SINGLE_RE.sub("'<val>'", text)
    text = _QUOTED_DOUBLE_RE.sub('"<val>"', text)
    text = _LONG_NUM_RE.sub("<num>", text)
    return text.strip()


def post_signal(component: str, description: str, source_container: str, raw_excerpt: str, severity: str) -> None:
    if not INTERNAL_SIGNAL_KEY:
        logger.error("INTERNAL_SIGNAL_KEY not set — dropping signal instead of posting unauthenticated")
        return
    try:
        resp = requests.post(
            f"{BACKEND_INTERNAL_URL}/internal/reliability/log-signal",
            json={
                "component": component,
                "description": description,
                "source_container": source_container,
                "raw_excerpt": raw_excerpt[:2000],
                "severity": severity,
            },
            headers={"X-Internal-Key": INTERNAL_SIGNAL_KEY},
            timeout=5,
        )
        if resp.status_code != 200:
            logger.warning("post_signal rejected (%s): %s", resp.status_code, resp.text[:300])
        else:
            logger.info("posted signal: %s", description[:120])
    except Exception as exc:
        logger.error("post_signal request failed: %s", exc)


class ContainerFollower(threading.Thread):
    """Follows one container's log stream, matching patterns line-by-line."""

    def __init__(self, client: "docker.DockerClient", container_name: str):
        super().__init__(daemon=True)
        self.client = client
        self.container_name = container_name
        self._stop = threading.Event()
        self._traceback_buf: list[str] = []

    def stop(self) -> None:
        self._stop.set()

    def _handle_traceback_buffering(self, line: str) -> bool:
        """Returns True if the line was consumed as part of traceback handling."""
        if TRACEBACK_START.match(line):
            self._traceback_buf = [line]
            return True

        if not self._traceback_buf:
            return False

        if line.startswith((" ", "\t")):
            # Frame line ("File ...", or the source excerpt) — keep buffering.
            self._traceback_buf.append(line)
            return True

        # First non-indented line after the traceback start is the exception
        # line — Python's traceback format guarantees exactly one such line
        # terminates the block.
        self._traceback_buf.append(line)
        buf, self._traceback_buf = self._traceback_buf, []

        exception_line = buf[-1].strip()
        exc_class = exception_line.split(":", 1)[0].strip()
        last_frame: Optional[str] = None
        for frame_line in buf:
            m = FILE_LINE_RE.search(frame_line)
            if m:
                last_frame = f"{m.group(1)}:{m.group(2)}"

        # Fingerprint on (exception class, innermost frame location) rather
        # than the free-text message — the message may carry PHI, the type
        # and location don't.
        description = f"backend_exception: {exc_class} at {last_frame or 'unknown_location'}"
        post_signal(
            component="backend_exception",
            description=description,
            source_container="royan_backend",
            raw_excerpt="\n".join(buf),
            severity="high",
        )
        return True

    def _handle_line(self, line: str) -> None:
        stripped_name = self.container_name.lstrip("/")

        if stripped_name == "royan_backend" and self._handle_traceback_buffering(line):
            return

        for pattern, severity in PATTERNS.get(stripped_name, []):
            if pattern.search(line):
                component = stripped_name.replace("royan_", "")
                fingerprint = normalize(line)
                post_signal(
                    component=component,
                    description=f"{component}: {fingerprint}",
                    source_container=stripped_name,
                    raw_excerpt=line,
                    severity=severity,
                )
                return

    def run(self) -> None:
        try:
            container = self.client.containers.get(self.container_name)
        except Exception as exc:
            logger.warning("could not attach to %s: %s", self.container_name, exc)
            return

        logger.info("following logs for %s", self.container_name)
        try:
            for raw_line in container.logs(stream=True, follow=True, since=int(time.time())):
                if self._stop.is_set():
                    break
                try:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                except Exception:
                    continue
                if line:
                    self._handle_line(line)
        except Exception as exc:
            logger.warning("log stream for %s ended: %s", self.container_name, exc)


def main() -> None:
    if not INTERNAL_SIGNAL_KEY:
        logger.error(
            "INTERNAL_SIGNAL_KEY is not set — refusing to start "
            "(would post unauthenticated signals that the backend will always reject)."
        )
        return

    client = docker.DockerClient(base_url=DOCKER_PROXY_URL)
    followers: dict[str, ContainerFollower] = {}

    logger.info("log-tail watcher starting, watching: %s", ", ".join(sorted(WATCHED_CONTAINERS)))

    while True:
        try:
            containers = client.containers.list(filters={"status": "running"})
            live_names = {c.name for c in containers if c.name in WATCHED_CONTAINERS}

            for name in live_names:
                existing = followers.get(name)
                if existing is None or not existing.is_alive():
                    follower = ContainerFollower(client, name)
                    follower.start()
                    followers[name] = follower

            for name in list(followers.keys()):
                if name not in live_names and not followers[name].is_alive():
                    del followers[name]
        except Exception as exc:
            logger.error("container discovery loop failed: %s", exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
