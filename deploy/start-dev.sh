#!/usr/bin/env bash
# One-command demo startup.
# Docker builds all frontend apps internally — no pre-build step needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# In WSL 2, the Linux docker binary is not installed — Docker Desktop runs on
# the Windows host. docker.exe is always on the WSL PATH when Docker Desktop
# is running, so use that instead.
if grep -qi microsoft /proc/version 2>/dev/null; then
    DOCKER="docker.exe"
else
    DOCKER="docker"
fi

echo "[docker] Using: ${DOCKER}"
echo "[docker] Tearing down old volumes..."
cd "${ROOT}/deploy"
"${DOCKER}" compose down -v 2>/dev/null || true

echo "[docker] Building and starting full stack..."
"${DOCKER}" compose up --build "$@"
