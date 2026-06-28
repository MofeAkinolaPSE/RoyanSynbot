#!/usr/bin/env bash
# Full reset — wipes ALL database data, volumes, and containers, then rebuilds.
# Use this only when you intentionally want a clean slate (e.g. demo prep, schema
# conflicts, corrupted DB).  Normal rebuilds should use start-dev.sh instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if grep -qi microsoft /proc/version 2>/dev/null; then
    DOCKER="docker.exe"
else
    DOCKER="docker"
fi

echo ""
echo "==========================================================="
echo "  WARNING: FULL RESET"
echo "  This will permanently DELETE:"
echo "    - All patient records"
echo "    - All staff accounts (including your login)"
echo "    - All billing, lab, and clinical data"
echo "    - All database volumes"
echo ""
echo "  The admin account will be re-seeded from .env after restart."
echo "  Everything else will be gone."
echo "==========================================================="
echo ""
read -p "Type RESET to confirm, or anything else to cancel: " confirm

if [ "${confirm}" != "RESET" ]; then
    echo "Cancelled. No changes made."
    exit 0
fi

echo ""
echo "[reset] Removing all containers and volumes..."
cd "${ROOT}/deploy"
"${DOCKER}" compose down -v 2>/dev/null || true

echo "[reset] Building and starting fresh stack..."
"${DOCKER}" compose up -d --build

echo ""
echo "[reset] Done. Admin account re-seeded from ADMIN_EMAIL / ADMIN_PASSWORD in .env"
echo "[reset] Log in with your .env credentials."
