#!/usr/bin/env bash
# Hardens SSH daemon configuration.
# Idempotent: backs up sshd_config before touching it.
set -euo pipefail

SSHD_CONFIG="/etc/ssh/sshd_config"
BACKUP="${SSHD_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"

[[ -f "${SSHD_CONFIG}" ]] || { echo "[ssh] sshd_config not found — skipping."; exit 0; }

cp "${SSHD_CONFIG}" "${BACKUP}"
echo "[ssh] Backed up sshd_config to ${BACKUP}"

_set() {
    local key="$1" val="$2"
    if grep -qE "^#?\\s*${key}\s" "${SSHD_CONFIG}"; then
        sed -i "s|^#\?\s*${key}\s.*|${key} ${val}|" "${SSHD_CONFIG}"
    else
        echo "${key} ${val}" >> "${SSHD_CONFIG}"
    fi
}

_set "PermitRootLogin"            "no"
_set "PasswordAuthentication"     "no"
_set "ChallengeResponseAuthentication" "no"
_set "UsePAM"                     "yes"
_set "MaxAuthTries"               "3"
_set "LoginGraceTime"             "30"
_set "ClientAliveInterval"        "300"
_set "ClientAliveCountMax"        "2"
_set "X11Forwarding"              "no"
_set "AllowTcpForwarding"         "no"
_set "PrintMotd"                  "no"

# Validate config before restarting
sshd -t || { echo "[ssh] sshd_config validation failed — restoring backup."; cp "${BACKUP}" "${SSHD_CONFIG}"; exit 1; }

systemctl restart sshd 2>/dev/null || service ssh restart 2>/dev/null || true
echo "[ssh] Hardening applied and sshd restarted."
echo "[ssh] WARNING: Ensure your SSH key is in authorized_keys BEFORE disconnecting."
