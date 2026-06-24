#!/usr/bin/env bash
# Watchdog — monitors Royan stack services and triggers a redeploy if
# any service falls below its desired replica count.
# Runs as a long-lived systemd service (watchdog.service).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_NAME="royan"
INTERVAL=60   # seconds between checks
MAX_FAILURES=3
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.swarm.yml"
LOG_PREFIX="[watchdog]"

consecutive_failures=0

_log() { echo "$(date '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} $*"; }

while true; do
    sleep "${INTERVAL}"

    degraded=()
    while IFS= read -r line; do
        svc_name=$(echo "${line}" | awk '{print $2}')
        replicas=$(echo "${line}" | awk '{print $4}')
        desired=$(echo "${replicas}" | cut -d/ -f2)
        actual=$(echo "${replicas}"  | cut -d/ -f1)
        if [[ "${actual}" != "${desired}" ]]; then
            degraded+=("${svc_name} ${actual}/${desired}")
        fi
    done < <(docker service ls --filter "label=com.docker.stack.namespace=${STACK_NAME}" 2>/dev/null || true)

    if (( ${#degraded[@]} == 0 )); then
        consecutive_failures=0
        _log "All services healthy."
        continue
    fi

    _log "Degraded services: ${degraded[*]}"
    (( consecutive_failures++ )) || true

    if (( consecutive_failures >= MAX_FAILURES )); then
        _log "ALERT: ${consecutive_failures} consecutive failures — triggering stack redeploy."
        consecutive_failures=0
        # shellcheck source=/dev/null
        set -a; source "${SCRIPT_DIR}/.env" 2>/dev/null || true; set +a
        docker stack deploy \
            --compose-file "${COMPOSE_FILE}" \
            --with-registry-auth \
            "${STACK_NAME}" 2>&1 | while IFS= read -r l; do _log "${l}"; done
    else
        _log "Failure ${consecutive_failures}/${MAX_FAILURES} — will retry."
    fi
done
