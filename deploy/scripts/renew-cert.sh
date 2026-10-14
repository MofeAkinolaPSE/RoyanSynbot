#!/bin/sh
# Royan Hospital — Let's Encrypt renewal
#
# Let's Encrypt certificates expire every 90 days. Add this to the SERVER's
# (host, not container) crontab to renew automatically — certbot only
# actually renews within 30 days of expiry, so running this weekly is a safe
# no-op most of the time. Run from the deploy/ directory:
#
#   crontab -e
#   0 3 * * 1  cd /path/to/RoyanSynbot/deploy && ./scripts/renew-cert.sh your-domain.example >> /var/log/royan-cert-renew.log 2>&1

set -e

DOMAIN="${1:?Usage: renew-cert.sh <domain>}"

echo "[$(date)] Checking for renewal of ${DOMAIN} ..."
docker compose run --rm certbot renew --webroot -w /var/www/certbot --quiet

echo "[$(date)] Re-installing certificate for nginx (idempotent if unchanged) ..."
docker compose run --rm --entrypoint sh certbot -c "
  cp /etc/letsencrypt/live/${DOMAIN}/fullchain.pem /etc/nginx/ssl/cert.pem &&
  cp /etc/letsencrypt/live/${DOMAIN}/privkey.pem /etc/nginx/ssl/key.pem
"
docker compose exec nginx nginx -s reload

echo "[$(date)] Done."
