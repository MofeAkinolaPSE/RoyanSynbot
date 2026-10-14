"""Which worker process runs the background jobs.

The API runs as several worker processes (UVICORN_WORKERS) so one slow request no longer holds up
everyone else. Background loops - escalations, the KPI watchdog, the workflow processor, monitors,
agents - must still run exactly once, so the first worker to take an exclusive lock on a file
becomes the leader and starts them; the others serve requests only. The lock is held for the
process's lifetime and released by the OS when it exits, so a restarted worker can take over.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)
_LOCK_PATH = os.getenv("BACKGROUND_LOCK_FILE", "/tmp/royan-background.lock")
_state: dict = {}


def is_leader() -> bool:
    if "leader" in _state:
        return _state["leader"]
    try:
        import fcntl
    except ImportError:          # not POSIX (local dev on Windows): a single process is always the leader
        _state["leader"] = True
        return True
    fh = open(_LOCK_PATH, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _state["fh"] = fh          # keep it open: closing it would release the lock
        _state["leader"] = True
        log.info("worker %s runs the background jobs", os.getpid())
    except OSError:
        fh.close()
        _state["leader"] = False
        log.info("worker %s serves requests only", os.getpid())
    return _state["leader"]
