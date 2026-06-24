#!/usr/bin/env bash
# Generates a self-signed TLS certificate for Nginx.
# Idempotent: skips if cert already exists and is not expired.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSL_DIR="${SCRIPT_DIR}/nginx/ssl"
CERT="${SSL_DIR}/cert.pem"
KEY="${SSL_DIR}/key.pem"
DOMAIN="${DOMAIN:-royan-hospital.local}"
VALIDITY_DAYS=365

mkdir -p "${SSL_DIR}"

if [[ -f "${CERT}" ]]; then
    expiry=$(openssl x509 -enddate -noout -in "${CERT}" 2>/dev/null | cut -d= -f2)
    expiry_epoch=$(date -d "${expiry}" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "${expiry}" +%s 2>/dev/null || echo 0)
    now_epoch=$(date +%s)
    days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
    if (( days_left > 30 )); then
        echo "[tls] Certificate valid for ${days_left} more days — skipping generation."
        exit 0
    fi
    echo "[tls] Certificate expires in ${days_left} days — regenerating."
fi

echo "[tls] Generating self-signed certificate for ${DOMAIN} (valid ${VALIDITY_DAYS} days)..."
openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "${KEY}" \
    -out "${CERT}" \
    -days "${VALIDITY_DAYS}" \
    -subj "/C=NG/ST=Lagos/L=Lagos/O=Royan Hospital/CN=${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN},DNS:localhost,IP:127.0.0.1"

chmod 600 "${KEY}"
chmod 644 "${CERT}"
echo "[tls] Certificate written to ${SSL_DIR}/"
