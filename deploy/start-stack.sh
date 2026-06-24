#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# Royan Hospital — Production Stack Deployer
# ════════════════════════════════════════════════════════════════════════════
# Usage:
#   sudo bash start-stack.sh --first-run [--install-deps] [--reset-db] [--tls-letsencrypt]
#   sudo bash start-stack.sh --redeploy  [--tls-letsencrypt]
#   sudo bash start-stack.sh --help
#
# Modes:
#   --first-run     Bootstrap a new server: hardens SSH, firewall, fail2ban,
#                   then builds images and deploys the Swarm stack.
#   --redeploy      Rebuild images and update the running stack in-place.
#
# Options:
#   --install-deps  apt-get install Docker, UFW, fail2ban, openssl, jq
#   --reset-db      Destroy all database volumes (requires typing YES)
#   --tls-letsencrypt  Request a Let's Encrypt cert after deployment
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
STACK_NAME="royan"
DEPLOY_DIR="/opt/royan"

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
_info()  { echo -e "${CYAN}[start-stack]${NC} $*"; }
_ok()    { echo -e "${GREEN}[start-stack]${NC} $*"; }
_warn()  { echo -e "${YELLOW}[start-stack] WARN:${NC} $*"; }
_fatal() { echo -e "${RED}[start-stack] FATAL:${NC} $*" >&2; exit 1; }

# ── Argument parsing ───────────────────────────────────────────────────────
MODE=""
INSTALL_DEPS=false
RESET_DB=false
TLS_LETSENCRYPT=false

usage() {
    grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

for arg in "$@"; do
    case "${arg}" in
        --first-run)        MODE="first-run" ;;
        --redeploy)         MODE="redeploy" ;;
        --install-deps)     INSTALL_DEPS=true ;;
        --reset-db)         RESET_DB=true ;;
        --tls-letsencrypt)  TLS_LETSENCRYPT=true ;;
        --help|-h)          usage ;;
        *) _fatal "Unknown argument: ${arg}. Run with --help." ;;
    esac
done

[[ -n "${MODE}" ]] || _fatal "Specify --first-run or --redeploy. Run with --help."
[[ "${EUID}" -eq 0 ]] || _fatal "Must run as root: sudo bash start-stack.sh ${*}"

# ── Step 0: Install host dependencies ─────────────────────────────────────
if [[ "${INSTALL_DEPS}" == "true" ]]; then
    _info "Installing host dependencies..."
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        docker.io docker-compose-v2 ufw fail2ban openssl jq curl
    systemctl enable --now docker
    _ok "Host dependencies installed."
fi

# ── Step 1: Destructive DB reset (explicit gate) ───────────────────────────
if [[ "${RESET_DB}" == "true" ]]; then
    _warn "You requested --reset-db. This will PERMANENTLY DELETE all database data."
    echo -n "  Type YES (uppercase) to confirm: "
    read -r confirmation
    [[ "${confirmation}" == "YES" ]] || _fatal "Reset cancelled."
    _info "Removing database volumes..."
    docker volume rm "${STACK_NAME}_db_data" 2>/dev/null || true
    _ok "Database volumes removed."
fi

# ── Step 2: Copy repo to deploy root (idempotent) ─────────────────────────
if [[ "${REPO_ROOT}" != "${DEPLOY_DIR}" ]]; then
    _info "Syncing repo to ${DEPLOY_DIR}..."
    mkdir -p "${DEPLOY_DIR}"
    rsync -a --exclude='.git' --exclude='.venv' --exclude='node_modules' \
        "${REPO_ROOT}/" "${DEPLOY_DIR}/"
    SCRIPT_DIR="${DEPLOY_DIR}/deploy"
    ENV_FILE="${SCRIPT_DIR}/.env"
fi

# ── Step 3: Verify .env present ────────────────────────────────────────────
[[ -f "${ENV_FILE}" ]] || _fatal ".env not found at ${ENV_FILE}. Copy .env.example and fill values."
# shellcheck source=/dev/null
set -a; source "${ENV_FILE}"; set +a

# ── Step 4: Pre-flight checks ──────────────────────────────────────────────
_info "Running pre-flight checks..."
bash "${SCRIPT_DIR}/preflight-host.sh"
_ok "Pre-flight passed."

# ── Step 5: Security hardening (first-run only) ────────────────────────────
if [[ "${MODE}" == "first-run" ]]; then
    _info "Applying SSH hardening..."
    bash "${SCRIPT_DIR}/harden-ssh.sh"

    _info "Configuring firewall..."
    bash "${SCRIPT_DIR}/setup-firewall.sh"

    _info "Configuring fail2ban..."
    bash "${SCRIPT_DIR}/setup-fail2ban.sh"

    _ok "Security hardening complete."
fi

# ── Step 6: Build images and deploy Swarm stack ────────────────────────────
_info "Running Swarm init + image build + stack deploy..."
bash "${SCRIPT_DIR}/init-swarm.sh"
_ok "Stack deployed."

# ── Step 7: Post-deploy probes ─────────────────────────────────────────────
_info "Running post-deploy health probes..."

# Give nginx a moment to come up
sleep 5

# 7a. DB connectivity from backend container
BACKEND_CONTAINER=$(docker ps --filter "name=royan_backend" -q | head -1 || true)
if [[ -n "${BACKEND_CONTAINER}" ]]; then
    docker exec "${BACKEND_CONTAINER}" python -c \
        "import psycopg2, os; psycopg2.connect(host=os.environ['POSTGRES_HOST'], dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD']); print('DB connection OK')" \
        2>/dev/null && _ok "DB connectivity: OK" || _warn "DB connectivity probe failed — check logs."
else
    _warn "Could not find backend container for DB probe."
fi

# 7b. HTTP health endpoint (via nginx proxy)
if curl -fsk --max-time 10 "http://localhost/api/health" >/dev/null 2>&1; then
    _ok "HTTP /api/health: OK"
else
    _warn "/api/health probe failed. Nginx may still be starting — check: docker service ls"
fi

# 7c. Auth endpoint smoke test
if [[ -n "${ADMIN_USERNAME:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
    auth_status=$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" \
        -X POST "http://localhost/api/token" \
        -d "username=${ADMIN_USERNAME}&password=${ADMIN_PASSWORD}" \
        -H "Content-Type: application/x-www-form-urlencoded" 2>/dev/null || echo "000")
    if [[ "${auth_status}" == "200" ]]; then
        _ok "Auth probe (/api/token): 200 OK"
    else
        _warn "Auth probe returned HTTP ${auth_status}. Admin may not be seeded yet."
    fi
fi

# ── Step 8: Optional Let's Encrypt ────────────────────────────────────────
if [[ "${TLS_LETSENCRYPT}" == "true" ]]; then
    _info "Provisioning Let's Encrypt certificate for ${DOMAIN:-}..."
    bash "${SCRIPT_DIR}/setup-letsencrypt.sh"
    _ok "TLS certificate provisioned."
fi

# ── Step 9: Install systemd watchdog and backup units ─────────────────────
_info "Installing systemd service units..."

_install_unit() {
    local name="$1"
    local src="${SCRIPT_DIR}/${name}"
    local dst="/etc/systemd/system/${name}"
    # Patch ExecStart path to actual deploy dir
    sed "s|/opt/royan|${DEPLOY_DIR}|g" "${src}" > "${dst}"
}

_install_unit "watchdog.service"
_install_unit "backup.service"
_install_unit "backup.timer"

# watchdog.sh must be executable from the deployed path
chmod +x "${DEPLOY_DIR}/deploy/watchdog.sh"

systemctl daemon-reload
systemctl enable --now royan-watchdog 2>/dev/null || systemctl enable --now watchdog 2>/dev/null || \
    systemctl enable --now "${DEPLOY_DIR}/deploy/watchdog.service" 2>/dev/null || \
    { _warn "Could not enable watchdog via systemctl. Enable manually after deploy."; }

systemctl enable --now backup.timer
_ok "Systemd units installed."

# ── Step 10: Summary ───────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-$(hostname -I | awk '{print $1}')}"
cat <<EOF

${GREEN}════════════════════════════════════════════════════════════════${NC}
${GREEN}  Royan Hospital Stack — Deployment Complete${NC}
${GREEN}════════════════════════════════════════════════════════════════${NC}

  Stack name :  ${STACK_NAME}
  Mode       :  ${MODE}
  IMAGE_TAG  :  ${IMAGE_TAG:-latest}

  URLs (once DNS / hosts resolve):
    Admin UI  →  https://${DOMAIN}/
    Patient   →  https://${DOMAIN}/portal
    API       →  https://${DOMAIN}/api/

  Useful commands:
    docker service ls                     # All service replicas
    docker service logs royan_backend     # Backend logs
    sudo bash ${SCRIPT_DIR}/start-stack.sh --redeploy   # Update stack

EOF
