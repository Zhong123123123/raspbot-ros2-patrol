#!/usr/bin/env bash
# Install the patrol systemd service for boot-time auto-start.
#
# Usage:
#   sudo bash scripts/patrol-systemd-install.sh
#
# After install:
#   sudo systemctl start patrol
#   sudo systemctl status patrol
#   sudo journalctl -u patrol -f    (follow logs)

set -euo pipefail

SERVICE_NAME="patrol"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="${SCRIPT_DIR}"
USER_NAME="${SUDO_USER:-${USER}}"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌  Must run as root:  sudo bash scripts/patrol-systemd-install.sh"
    exit 1
fi

cat > "${SERVICE_FILE}" << 'UNIT'
[Unit]
Description=Raspbot Patrol Service (ROS2)
Documentation=https://github.com/your-org/raspbot
After=network.target multi-user.target
Wants=network.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__WS_DIR__
Environment=HOME=/home/__USER__

ExecStartPre=/bin/sleep 10

ExecStart=/bin/bash -c '\
    source /opt/ros/jazzy/setup.bash && \
    source __WS_DIR__/install/setup.bash && \
    export ROS_DOMAIN_ID=0 && \
    ros2 launch raspbot_bringup patrol_full.launch.py'

# Auto-restart on failure
Restart=on-failure
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=%n

# Security hardening (best-effort on Pi)
NoNewPrivileges=no
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT

# Fill in placeholders
sed -i "s|__USER__|${USER_NAME}|g" "${SERVICE_FILE}"
sed -i "s|__WS_DIR__|${WS_DIR}|g" "${SERVICE_FILE}"

echo "✅  Service written: ${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo ""
echo "   Installed and enabled. Commands:"
echo ""
echo "     sudo systemctl start patrol        # start now"
echo "     sudo systemctl stop patrol         # stop"
echo "     sudo systemctl status patrol       # check status"
echo "     sudo journalctl -u patrol -f       # follow logs"
echo "     sudo systemctl disable patrol      # disable auto-start"
echo ""
echo "   ⚠️  20s boot delay configured (ExecStartPre sleep 10)"
echo ""
