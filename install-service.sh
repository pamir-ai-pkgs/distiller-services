#!/bin/bash

# WiFi Setup Service Installation Script

set -e

SERVICE_NAME="wifi-setup"
SERVICE_FILE="wifi-setup.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "🔧 Installing WiFi Setup Service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: This script must be run as root"
    echo "Please run: sudo bash install-service.sh"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Error: $SERVICE_FILE not found in current directory"
    exit 1
fi

# Copy service file to systemd directory
echo "📁 Copying service file to $SYSTEMD_DIR/"
cp "$SERVICE_FILE" "$SYSTEMD_DIR/"

# Set proper permissions
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service
echo "✅ Enabling $SERVICE_NAME service..."
systemctl enable "$SERVICE_NAME"

# Check service status
echo "📊 Service status:"
systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "🎉 WiFi Setup Service installed successfully!"
echo ""
echo "Commands to manage the service:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Disable: sudo systemctl disable $SERVICE_NAME"
echo ""
echo "The service will now start automatically at boot."
echo "To start it now, run: sudo systemctl start $SERVICE_NAME" 