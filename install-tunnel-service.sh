#!/bin/bash
# Install script for Pinggy Tunnel Service

set -e

SERVICE_NAME="pinggy-tunnel"
SERVICE_FILE="${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Pinggy Tunnel Service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Make the Python script executable
chmod +x "${SCRIPT_DIR}/pinggy_tunnel_service.py"

# Copy service file
echo "Copying service file..."
cp "${SCRIPT_DIR}/${SERVICE_FILE}" "/etc/systemd/system/"

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Enable service
echo "Enabling service..."
systemctl enable ${SERVICE_NAME}

# Start service
echo "Starting service..."
systemctl start ${SERVICE_NAME}

# Show status
echo ""
echo "Service installed successfully!"
echo ""
echo "The tunnel service will:"
echo "  - Wait for network connectivity"
echo "  - Establish SSH tunnel through Pinggy (port 3000)"
echo "  - Display QR code on e-ink screen"
echo "  - Refresh tunnel every 55 minutes"
echo ""
echo "Commands:"
echo "  Check status:  sudo systemctl status ${SERVICE_NAME}"
echo "  View logs:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Restart:       sudo systemctl restart ${SERVICE_NAME}"
echo "  Stop:          sudo systemctl stop ${SERVICE_NAME}"
echo ""