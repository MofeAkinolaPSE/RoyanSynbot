#!/bin/sh
set -e

echo "=========================================="
echo "  RoyanHealth — Royan Hospital"
echo "=========================================="

echo "[1/2] Running database migrations..."
python scripts/apply_migrations.py

echo "[2/2] Starting API server..."
# Several worker processes, so one slow request no longer holds up everyone else (the API code makes
# blocking database calls). Background jobs run in one worker only (src/services/leader.py) and live
# updates reach every worker through Redis (src/services/realtime.py). Each worker's pool is sized so
# the total stays well under Postgres's max_connections (100): 3 x 25 = 75.
export UVICORN_WORKERS="${UVICORN_WORKERS:-3}"
export PG_MAX_CONN="${PG_MAX_CONN:-25}"
rm -f /tmp/royan-background.lock
# --proxy-headers / --forwarded-allow-ips: trust X-Forwarded-Proto/For from nginx (the only thing that can reach this
# port - it is not published), so redirects the app builds say https:// and keep the public port (:9443).
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "$UVICORN_WORKERS" --proxy-headers --forwarded-allow-ips "*"
