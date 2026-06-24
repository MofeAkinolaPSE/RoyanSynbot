#!/usr/bin/env bash
# Pre-flight checks. Must pass before any deployment step runs.
# Exit 1 on first failure so start-stack.sh can abort cleanly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

_fail() { echo "[preflight] FAIL: $*" >&2; exit 1; }
_ok()   { echo "[preflight] OK:   $*"; }

# 1. Docker installed and daemon running
command -v docker >/dev/null 2>&1 || _fail "Docker not installed. Re-run with --install-deps."
docker info >/dev/null 2>&1       || _fail "Docker daemon not running. Start it: systemctl start docker"
_ok "Docker daemon reachable"

# 2. .env file present
[[ -f "${ENV_FILE}" ]] || _fail ".env not found at ${ENV_FILE}. Copy .env.example and fill values."
_ok ".env file present"

# shellcheck source=/dev/null
source "${ENV_FILE}"

# 3. Required env vars
REQUIRED_VARS=(
    POSTGRES_USER
    POSTGRES_PASSWORD
    POSTGRES_DB
    JWT_SECRET
    DEEPSEEK_API_KEY
    ADMIN_EMAIL
    ADMIN_USERNAME
    ADMIN_PASSWORD
)
missing=()
for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [[ -z "${val}" || "${val}" == CHANGE_THIS* || "${val}" == "sk-..." ]]; then
        missing+=("${var}")
    fi
done
if (( ${#missing[@]} > 0 )); then
    echo "[preflight] FAIL: Required env vars not set or still have placeholder values:" >&2
    printf "             %s\n" "${missing[@]}" >&2
    exit 1
fi
_ok "All required env vars present"

# 4. JWT_SECRET must be ≥ 32 chars
jwt_len=${#JWT_SECRET}
(( jwt_len >= 32 )) || _fail "JWT_SECRET too short (${jwt_len} chars). Use ≥ 32 random chars."
_ok "JWT_SECRET length OK (${jwt_len} chars)"

# 5. Free disk space ≥ 2 GB (on the partition where /var/lib/docker lives)
avail_kb=$(df /var/lib/docker 2>/dev/null | awk 'NR==2{print $4}' || df / | awk 'NR==2{print $4}')
avail_gb=$(( avail_kb / 1024 / 1024 ))
(( avail_gb >= 2 )) || _fail "Insufficient disk space: ${avail_gb} GB free. Need ≥ 2 GB."
_ok "Disk space OK (${avail_gb} GB free)"

# 6. openssl present (needed for TLS cert generation)
command -v openssl >/dev/null 2>&1 || _fail "openssl not found. Install: apt-get install openssl"
_ok "openssl available"

echo "[preflight] All checks passed."
