#!/usr/bin/env bash
# Installs and configures fail2ban to protect SSH and Nginx.
# Idempotent: creates jail configs under /etc/fail2ban/jail.d/
set -euo pipefail

command -v fail2ban-client >/dev/null 2>&1 || { echo "[fail2ban] fail2ban not found. Install: apt-get install fail2ban"; exit 1; }

JAIL_DIR="/etc/fail2ban/jail.d"
mkdir -p "${JAIL_DIR}"

cat > "${JAIL_DIR}/royan-sshd.conf" <<'EOF'
[sshd]
enabled   = true
port      = 22
filter    = sshd
logpath   = /var/log/auth.log
maxretry  = 5
bantime   = 3600
findtime  = 600
EOF

cat > "${JAIL_DIR}/royan-nginx.conf" <<'EOF'
[nginx-http-auth]
enabled   = true
filter    = nginx-http-auth
logpath   = /var/log/nginx/error.log
maxretry  = 5
bantime   = 3600
findtime  = 600
EOF

cat > "${JAIL_DIR}/royan-nginx-limit.conf" <<'EOF'
[nginx-limit-req]
enabled   = true
filter    = nginx-limit-req
logpath   = /var/log/nginx/error.log
maxretry  = 10
bantime   = 600
findtime  = 60
EOF

systemctl enable fail2ban
systemctl restart fail2ban

sleep 2
fail2ban-client status
echo "[fail2ban] Configured and active."
