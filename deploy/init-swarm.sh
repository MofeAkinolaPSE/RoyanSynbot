#!/usr/bin/env bash
# Initialises Docker Swarm, starts a local image registry, builds and pushes
# all service images, then deploys the Royan stack.
# Called by start-stack.sh — do not run standalone without setting env first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STACK_NAME="royan"
REGISTRY="localhost:5000"
IMAGE_TAG="${IMAGE_TAG:-latest}"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.swarm.yml"

# ── 1. Initialise Swarm ────────────────────────────────────────────────────
if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q "active"; then
    echo "[swarm] Initialising Docker Swarm..."
    docker swarm init --advertise-addr 127.0.0.1
else
    echo "[swarm] Swarm already active."
fi

# ── 2. Start local registry ────────────────────────────────────────────────
if ! docker service ls --filter name=registry -q 2>/dev/null | grep -q .; then
    if docker ps -a --filter name=registry -q 2>/dev/null | grep -q .; then
        docker start registry 2>/dev/null || true
    else
        docker run -d \
            --name registry \
            --restart unless-stopped \
            -p 127.0.0.1:5000:5000 \
            registry:2
    fi
    echo "[swarm] Local registry started at ${REGISTRY}"
else
    echo "[swarm] Registry already running."
fi

# ── 3. Trust localhost:5000 (insecure registry on loopback) ───────────────
DAEMON_JSON="/etc/docker/daemon.json"
if ! grep -q '"localhost:5000"' "${DAEMON_JSON}" 2>/dev/null; then
    echo "[swarm] Adding localhost:5000 to Docker insecure-registries..."
    if [[ -f "${DAEMON_JSON}" ]]; then
        # Merge into existing daemon.json (requires jq)
        if command -v jq >/dev/null 2>&1; then
            tmp=$(mktemp)
            jq '."insecure-registries" += ["localhost:5000"]' "${DAEMON_JSON}" > "${tmp}"
            mv "${tmp}" "${DAEMON_JSON}"
        else
            echo "[swarm] WARNING: jq not found. Manually add localhost:5000 to ${DAEMON_JSON} insecure-registries."
        fi
    else
        echo '{"insecure-registries":["localhost:5000"]}' > "${DAEMON_JSON}"
    fi
    systemctl reload docker 2>/dev/null || true
    sleep 3
fi
echo "[swarm] Registry trust configured."

# ── 4. Generate TLS certificate ────────────────────────────────────────────
bash "${SCRIPT_DIR}/gen-tls-cert.sh"

# ── 5. Build and push images ───────────────────────────────────────────────
_build_push() {
    local name="$1" context="$2" dockerfile="${3:-Dockerfile}"
    local image="${REGISTRY}/royan_${name}:${IMAGE_TAG}"
    echo "[swarm] Building ${name}..."
    docker build -t "${image}" -f "${context}/${dockerfile}" "${context}"
    docker push "${image}"
    # Also tag as latest for convenience
    if [[ "${IMAGE_TAG}" != "latest" ]]; then
        docker tag "${image}" "${REGISTRY}/royan_${name}:latest"
        docker push "${REGISTRY}/royan_${name}:latest"
    fi
    echo "[swarm] Pushed ${image}"
}

_build_push "backend"        "${REPO_ROOT}/backend"
_build_push "frontend"       "${REPO_ROOT}/SynbotUI"
_build_push "patient_portal" "${REPO_ROOT}/patient-portal"
_build_push "db"             "${REPO_ROOT}/backend/db/postgres-pgvector"

# ── 6. Export .env vars for docker stack deploy ────────────────────────────
# docker stack deploy does NOT read .env automatically.
# shellcheck source=/dev/null
set -a; source "${SCRIPT_DIR}/.env"; set +a
export IMAGE_TAG

# ── 7. Deploy stack ────────────────────────────────────────────────────────
echo "[swarm] Deploying stack '${STACK_NAME}'..."
docker stack deploy \
    --compose-file "${COMPOSE_FILE}" \
    --with-registry-auth \
    "${STACK_NAME}"

# ── 8. Wait for services to converge ──────────────────────────────────────
echo "[swarm] Waiting for services to converge (up to 120s)..."
deadline=$(( $(date +%s) + 120 ))
while (( $(date +%s) < deadline )); do
    not_ready=$(docker service ls --filter "label=com.docker.stack.namespace=${STACK_NAME}" \
        --format '{{.Replicas}}' | grep -v '^\([0-9]*\)/\1$' | wc -l || true)
    if [[ "${not_ready}" -eq 0 ]]; then
        echo "[swarm] All services converged."
        docker service ls --filter "label=com.docker.stack.namespace=${STACK_NAME}"
        exit 0
    fi
    echo "[swarm] ${not_ready} service(s) not yet ready — waiting..."
    sleep 8
done

echo "[swarm] WARNING: services did not fully converge within 120s. Check: docker service ls" >&2
docker service ls --filter "label=com.docker.stack.namespace=${STACK_NAME}"
exit 1
