#!/bin/bash
#
# Nova Platform - Systemd Service Installation Script
# Installs nova-server as a systemd service for auto-start on boot
#

set -e

SERVICE_NAME="nova-server"
SERVICE_USER="${SUDO_USER:-$(whoami)}"
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
NOVA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Nova Platform - Service Installer${NC}"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo $0${NC}"
    exit 1
fi

# Detect Python
PYTHON_BIN=$(which python3 || which python)

# Create nova .local bin dir if needed
mkdir -p "${SERVICE_HOME}/.local/bin"

echo "Service name: $SERVICE_NAME"
echo "User: $SERVICE_USER"
echo "Home: $SERVICE_HOME"
echo "Nova dir: $NOVA_DIR"
echo ""

# Create config if not exists
CONFIG_DIR="${SERVICE_HOME}/.nova-platform"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "${NOVA_DIR}/config.example.yaml" ]; then
        cp "${NOVA_DIR}/config.example.yaml" "$CONFIG_FILE"
        echo -e "${GREEN}Created config: $CONFIG_FILE${NC}"
        echo ""
        echo -e "${YELLOW}Note: Edit $CONFIG_FILE to set production environment${NC}"
        echo ""
    fi
fi

# Create systemd service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Nova Platform - AI Collaboration Platform
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$(id -gn "$SERVICE_USER")
WorkingDirectory=$NOVA_DIR
Environment="PATH=$SERVICE_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PYTHON_BIN -m nova server start --config "$CONFIG_FILE"
ExecStop=$PYTHON_BIN -m nova server stop
Restart=always
RestartSec=5
StandardOutput=append:$SERVICE_HOME/.nova-platform/nova-server.log
StandardError=append:$SERVICE_HOME/.nova-platform/nova-server.log

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$SERVICE_HOME/.nova-platform

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}Created: $SERVICE_FILE${NC}"

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable "$SERVICE_NAME"

echo ""
echo -e "${GREEN}Service installed successfully!${NC}"
echo ""
echo "Commands:"
echo "  systemctl start  $SERVICE_NAME   # Start server"
echo "  systemctl stop   $SERVICE_NAME   # Stop server"
echo "  systemctl status $SERVICE_NAME   # Check status"
echo "  journalctl -u $SERVICE_NAME -f   # View logs"
echo ""
echo "Or use nova CLI:"
echo "  nova server start"
echo "  nova server stop"
echo "  nova server status"
echo "  nova server config --show"
echo ""
