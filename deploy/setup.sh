#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 24.04 Droplet. Run as root: bash setup.sh
# Safe to re-run. Nothing here is app state: images come from GHCR, so a dead box is rebuilt with this script.
set -euo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl ufw unattended-upgrades

# Docker engine + compose plugin
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

# Swap: background removal peaks at ~2 GB, the same as the Droplet's RAM
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/99-stitchery.conf
sysctl --system >/dev/null

# Firewall: SSH and web only (the API container is never published)
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443
ufw --force enable

# Automatic security updates, rebooting at 04:00 when a kernel update needs it
cat > /etc/apt/apt.conf.d/52stitchery <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF

# Deploy user: GitHub Actions logs in as this user, by SSH key only
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
cat /root/.ssh/authorized_keys >> /home/deploy/.ssh/authorized_keys
sort -u -o /home/deploy/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
install -d -o deploy -g deploy /srv/stitchery

# Key-only SSH
cat > /etc/ssh/sshd_config.d/10-stitchery.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
EOF
systemctl reload ssh

echo "Done. Add the CI public key to /home/deploy/.ssh/authorized_keys, then push to main to deploy."
