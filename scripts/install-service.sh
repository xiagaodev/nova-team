#!/bin/bash
#
# Nova Platform - Systemd Service Installation Script
# Supports both system-wide and user-level installation
#

set -e

SERVICE_NAME="nova-server"
SERVICE_USER="${SUDO_USER:-$(whoami)}"
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
NOVA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default: user-level installation
USER_LEVEL=false

usage() {
    echo "Nova Platform - Service Installer"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --user-level   Install for current user (default)"
    echo "  --system       Install system-wide (requires root)"
    echo "  --uninstall    Remove the service"
    echo "  -h, --help     Show this help"
    exit 0
}

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --user-level) USER_LEVEL=true; shift ;;
        --system) USER_LEVEL=false; shift ;;
        --uninstall) UNINSTALL=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo -e "${GREEN}Nova Platform - Service Installer${NC}"
echo "========================================"
echo ""

# Detect Python
NOVA_BIN="${SERVICE_HOME}/.local/bin/nova"

# Config paths
CONFIG_DIR="${SERVICE_HOME}/.nova-platform"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
LOG_DIR="${SERVICE_HOME}/.nova-platform"
mkdir -p "$CONFIG_DIR" "$LOG_DIR"

if [ "$USER_LEVEL" = true ]; then
    SYSTEMD_USER_DIR="${SERVICE_HOME}/.config/systemd/user"
    SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
    mkdir -p "$SYSTEMD_USER_DIR"
    
    echo "Mode: User-level installation"
    echo "User: $SERVICE_USER"
    echo "Service file: $SERVICE_FILE"
    echo ""
    
    # Create config if not exists
    if [ ! -f "$CONFIG_FILE" ]; then
        if [ -f "${NOVA_DIR}/config.example.yaml" ]; then
            cp "${NOVA_DIR}/config.example.yaml" "$CONFIG_FILE"
            echo -e "${GREEN}Created config: $CONFIG_FILE${NC}"
            echo -e "${YELLOW}Note: Edit $CONFIG_FILE to set production environment${NC}"
            echo ""
        fi
    fi
    
    # Create systemd user service file
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Nova Platform - AI Collaboration Platform
After=default.target

[Service]
Type=forking
WorkingDirectory=$NOVA_DIR
Environment="PATH=$SERVICE_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$NOVA_BIN server start --config "$CONFIG_FILE"
ExecStop=$NOVA_BIN server stop
Restart=always
RestartSec=5
PIDFile=$LOG_DIR/nova-server.pid
StandardOutput=append:$LOG_DIR/nova-server.log
StandardError=append:$LOG_DIR/nova-server.log

# Hardening
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$LOG_DIR

[Install]
WantedBy=default.target
EOF

    echo -e "${GREEN}Created: $SERVICE_FILE${NC}"
    
    # Enable linger for user (allows service to run without user logged in)
    if ! loginctl show-user "$SERVICE_USER" 2>/dev/null | grep -q "Linger=yes"; then
        echo ""
        echo -e "${YELLOW}Note: Run 'loginctl enable-linger' as root to allow service to start without login:${NC}"
        echo "    sudo loginctl enable-linger $SERVICE_USER"
        echo ""
    fi
    
    # Reload systemd user
    systemctl --user daemon-reload
    
    # Enable service
    systemctl --user enable "$SERVICE_NAME"
    
    echo ""
    echo -e "${GREEN}Service installed successfully!${NC}"
    echo ""
    echo "Commands:"
    echo "  systemctl --user start  $SERVICE_NAME   # Start server"
    echo "  systemctl --user stop   $SERVICE_NAME   # Stop server"
    echo "  systemctl --user status $SERVICE_NAME   # Check status"
    echo "  journalctl --user -u $SERVICE_NAME -f   # View logs"
    echo ""
    echo "Or use nova CLI:"
    echo "  nova server start"
    echo "  nova server stop"
    echo "  nova server status"
    echo "  nova server config --show"
    echo ""

else
    # System-wide installation (requires root)
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}System-wide installation requires root. Run with sudo or use --user-level${NC}"
        exit 1
    fi
    
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    
    echo "Mode: System-wide installation"
    echo "Service file: $SERVICE_FILE"
    echo ""
    
    # Create config if not exists
    if [ ! -f "$CONFIG_FILE" ]; then
        if [ -f "${NOVA_DIR}/config.example.yaml" ]; then
            cp "${NOVA_DIR}/config.example.yaml" "$CONFIG_FILE"
            echo -e "${GREEN}Created config: $CONFIG_FILE${NC}"
        fi
    fi
    
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
ExecStart=$NOVA_BIN server start --config "$CONFIG_FILE"
ExecStop=$NOVA_BIN server stop
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/nova-server.log
StandardError=append:$LOG_DIR/nova-server.log

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$LOG_DIR

[Install]
WantedBy=multi-user.target
EOF

    echo -e "${GREEN}Created: $SERVICE_FILE${NC}"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    
    echo ""
    echo -e "${GREEN}Service installed successfully!${NC}"
    echo ""
    echo "Commands:"
    echo "  systemctl start  $SERVICE_NAME"
    echo "  systemctl stop   $SERVICE_NAME"
    echo "  systemctl status $SERVICE_NAME"
    echo "  journalctl -u $SERVICE_NAME -f"
fi
