#!/usr/bin/env bash
# Configures UFW firewall for Royan Hospital deployment.
# Idempotent: UFW rules are additive and safe to re-apply.
set -euo pipefail

command -v ufw >/dev/null 2>&1 || { echo "[firewall] ufw not found. Install: apt-get install ufw"; exit 1; }

echo "[firewall] Configuring UFW rules..."

# Default deny incoming, allow outgoing
ufw --force default deny incoming
ufw --force default allow outgoing

# SSH — must come before enable or you'll lock yourself out
ufw allow 22/tcp   comment "SSH"

# Web
ufw allow 80/tcp   comment "HTTP (redirect to HTTPS)"
ufw allow 443/tcp  comment "HTTPS"

# Docker Swarm management (manager port — only needed if multi-node later)
ufw allow 2377/tcp comment "Docker Swarm manager"

# Docker overlay networking (needed even on single-node for attachable net debug)
ufw allow 4789/udp comment "Docker overlay VXLAN"
ufw allow 7946/tcp comment "Docker Swarm node gossip"
ufw allow 7946/udp comment "Docker Swarm node gossip"

# Enable without interactive prompt
ufw --force enable
ufw status verbose

echo "[firewall] UFW configured and enabled."
