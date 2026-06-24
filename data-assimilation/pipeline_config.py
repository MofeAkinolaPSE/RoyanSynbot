"""Pipeline configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class PipelineConfig:
    max_workers: int = int(os.environ.get("PIPELINE_MAX_WORKERS", "4"))
    circuit_breaker_threshold: int = 3
    incremental_lookback_hours: int = 2     # overlap window for late-arriving rows
    dlq_batch_size: int = 100
    gold_refresh_enabled: bool = True
    redis_url: Optional[str] = os.environ.get("REDIS_URL") or None
    log_format: str = os.environ.get("LOG_FORMAT", "console")  # "json" | "console"
    default_mode: str = os.environ.get("PIPELINE_MODE", "full")
