#!/usr/bin/env bash
# Provisions a Let's Encrypt certificate via certbot.
# Requires: DOMAIN and ADMIN_EMAIL env vars; nginx running on port 80.
# Only run after DNS is pointed at this server.
#
# NOTE: this script is for the Docker SWARM deployment path (start-stack.sh,
# `docker service update`, host-level nginx + certbot via apt). If you're
# running the plain `docker compose up -d` deployment (the one DEPLOYMENT.md's
# main walkthrough uses, with a containerized nginx), use
# deploy/scripts/issue-cert.sh and deploy/scripts/renew-cert.sh instead — this
# script's `docker service update` call will fail outside a Swarm.
set -euo pipefail

: "${DOMAIN:?DOMAIN env var required (e.g. hospital.example.ng)}"
: "${ADMIN_EMAIL:?ADMIN_EMAIL env var required}"

command -v certbot >/dev/null 2>&1 || {
    echo "[letsencrypt] certbot not found — installing..."
    apt-get install -y certbot python3-certbot-nginx
}

echo "[letsencrypt] Requesting certificate for ${DOMAIN}..."
certbot --nginx \
    --non-interactive \
    --agree-tos \
    --email "${ADMIN_EMAIL}" \
    --domains "${DOMAIN}" \
    --redirect

# Reload nginx inside the swarm service to pick up new cert
docker service update --force royan_nginx 2>/dev/null || true

# Certbot auto-renewal via systemd timer is enabled by the package.
# Verify it exists:
if systemctl is-active --quiet certbot.timer 2>/dev/null; then
    echo "[letsencrypt] Auto-renewal timer active."
else
    echo "[letsencrypt] NOTE: certbot.timer not found. Set up cron: 0 3 * * * certbot renew --quiet"
fi

echo "[letsencrypt] Certificate provisioned for ${DOMAIN}."
