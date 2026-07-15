#!/bin/sh
# Royan Hospital — One-time Let's Encrypt certificate issuance
#
# Run this ONCE the domain's DNS A record points at this server's public IP,
# and ports 80 + 443 are reachable from the internet. Run from the deploy/
# directory (same place you run `docker compose up`):
#
#   ./scripts/issue-cert.sh your-domain.example admin@your-domain.example
#
# After it succeeds, the self-signed cert is replaced and nginx is reloaded —
# no other steps needed. Safe to re-run.

set -e

DOMAIN="${1:?Usage: issue-cert.sh <domain> <email>}"
EMAIL="${2:?Usage: issue-cert.sh <domain> <email>}"

echo "[1/3] Requesting certificate for ${DOMAIN} ..."
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${EMAIL}" --agree-tos --no-eff-email --non-interactive

echo "[2/3] Installing certificate for nginx ..."
docker compose run --rm --entrypoint sh certbot -c "
  cp /etc/letsencrypt/live/${DOMAIN}/fullchain.pem /nginx-ssl/cert.pem &&
  cp /etc/letsencrypt/live/${DOMAIN}/privkey.pem /nginx-ssl/key.pem
"

echo "[3/3] Reloading nginx ..."
docker compose restart nginx

echo "Done. Verify with: curl -I https://${DOMAIN}/"
echo "Now add renewal to the server's crontab — see scripts/renew-cert.sh."
