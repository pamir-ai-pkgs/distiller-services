#!/bin/bash

# Distiller CM5 Pinggy Tunnel Service Installation Script
# Installs the Pinggy tunnel service for remote access
# Updated for current project structure and better error handling

set -e

SERVICE_NAME="pinggy-tunnel"
SERVICE_FILE="${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/distiller-cm5-services"
SYSTEMD_DIR="/etc/systemd/system"

echo "================================================================"
echo "Distiller CM5 Pinggy Tunnel Service Installation"
echo "Setting up remote access tunnel service..."
echo "================================================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Please run: sudo bash install-tunnel-service.sh"
    exit 1
fi

# Detect system information
echo "Detecting system information..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "   OS: $PRETTY_NAME"
    echo "   Architecture: $(uname -m)"
fi

# Install system dependencies for tunnel service
echo "Installing system dependencies..."
apt-get update -qq
apt-get install -y \
    python3 \
    python3-pip \
    openssh-client \
    curl \
    systemd \
    qrencode || echo "Warning: Some packages may not be available on this system"

# Create installation directory if it doesn't exist
echo "Ensuring installation directory exists: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy tunnel service files
echo "Copying tunnel service files..."
if [ -f "${SCRIPT_DIR}/pinggy_tunnel_service.py" ]; then
    cp "${SCRIPT_DIR}/pinggy_tunnel_service.py" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/pinggy_tunnel_service.py"
else
    echo "Error: pinggy_tunnel_service.py not found in $SCRIPT_DIR"
    exit 1
fi

# Copy WiFi display script if it exists (for e-ink functionality)

if [ -f "${SCRIPT_DIR}/wifi_info_display.py" ]; then
    cp "${SCRIPT_DIR}/wifi_info_display.py" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/wifi_info_display.py"
    echo "   WiFi info display script copied"
fi

# Copy fonts directory if it exists
if [ -d "${SCRIPT_DIR}/fonts" ]; then
    cp -r "${SCRIPT_DIR}/fonts" "$INSTALL_DIR/"
    echo "   Fonts directory copied"
fi

# Set up Python environment if not already done
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
"$VENV_DIR/bin/pip" install --upgrade pip

# Install Python dependencies for tunnel service
echo "Installing tunnel service dependencies..."
"$VENV_DIR/bin/pip" install \
    requests \
    qrcode[pil] \
    pillow \
    psutil \
    subprocess-tee || echo "Warning: Some Python packages may not install correctly"

# Create updated service file
echo "Creating systemd service file..."
cat >"$SYSTEMD_DIR/$SERVICE_FILE" <<EOF
[Unit]
Description=Distiller CM5 Pinggy Tunnel Service
After=network-online.target
Wants=network-online.target
Requires=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$VENV_DIR/bin
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/pinggy_tunnel_service.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Wait for network connectivity before starting
ExecStartPre=/bin/bash -c 'until ping -c1 8.8.8.8; do sleep 5; done'

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

# Set ownership
chown -R root:root "$INSTALL_DIR"

# Create tunnel management script
echo "Creating tunnel management script..."
cat >"$INSTALL_DIR/manage-tunnel.sh" <<'EOF'
#!/bin/bash

SERVICE_NAME="pinggy-tunnel"

case "$1" in
    start)
        echo "Starting tunnel service..."
        systemctl start $SERVICE_NAME
        ;;
    stop)
        echo "Stopping tunnel service..."
        systemctl stop $SERVICE_NAME
        ;;
    restart)
        echo "Restarting tunnel service..."
        systemctl restart $SERVICE_NAME
        ;;
    status)
        echo "=== Tunnel Service Status ==="
        systemctl status $SERVICE_NAME --no-pager -l
        echo ""
        echo "=== Recent Logs ==="
        journalctl -u $SERVICE_NAME -n 20 --no-pager
        ;;
    logs)
        echo "=== Live Tunnel Logs ==="
        journalctl -u $SERVICE_NAME -f
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the tunnel service"
        echo "  stop    - Stop the tunnel service"
        echo "  restart - Restart the tunnel service"
        echo "  status  - Show service status and recent logs"
        echo "  logs    - Show live logs"
        exit 1
        ;;
esac
EOF

chmod +x "$INSTALL_DIR/manage-tunnel.sh"

# Create tunnel uninstall script
echo "Creating uninstall script..."
cat >"$INSTALL_DIR/uninstall-tunnel.sh" <<EOF
#!/bin/bash
echo "Uninstalling Pinggy Tunnel Service..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl disable $SERVICE_NAME 2>/dev/null || true
rm -f "$SYSTEMD_DIR/$SERVICE_FILE"
systemctl daemon-reload
echo "Tunnel service uninstalled."
echo "Note: Main installation directory $INSTALL_DIR preserved."
echo "To remove tunnel scripts: rm -f $INSTALL_DIR/pinggy_tunnel_service.py $INSTALL_DIR/*display*.py"
EOF

chmod +x "$INSTALL_DIR/uninstall-tunnel.sh"

# Reload systemd and enable service
echo "Configuring systemd service..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}

# Check if main WiFi service exists and offer to start tunnel
WIFI_SERVICE_STATUS=$(systemctl is-enabled distiller-wifi 2>/dev/null || echo "not-found")

echo ""
echo "Tunnel service installation complete!"
echo ""
echo "Service Information:"
echo "   Service Name: $SERVICE_NAME"
echo "   Install Directory: $INSTALL_DIR"
echo "   Python Environment: $VENV_DIR"
echo ""
echo "Management Commands:"
echo "   Quick management:  sudo $INSTALL_DIR/manage-tunnel.sh {start|stop|status|logs}"
echo "   Start service:     sudo systemctl start $SERVICE_NAME"
echo "   Stop service:      sudo systemctl stop $SERVICE_NAME"
echo "   Check status:      sudo systemctl status $SERVICE_NAME"
echo "   View logs:         sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Advanced:"
echo "   Uninstall tunnel:  sudo $INSTALL_DIR/uninstall-tunnel.sh"
echo ""
echo "What the tunnel service does:"
echo "   • Waits for network connectivity"
echo "   • Establishes SSH tunnel through Pinggy (port 3000)"
echo "   • Displays QR code on e-ink screen (if available)"
echo "   • Refreshes tunnel every 55 minutes"
echo "   • Provides remote access to your device"
echo ""

if [ "$WIFI_SERVICE_STATUS" != "not-found" ]; then
    echo "WiFi service detected. Both services can run together."
else
    echo "Info: WiFi service not detected. Install with: sudo ./install-service.sh"
fi

echo ""
echo "Next steps:"
echo "   1. Start the service: sudo systemctl start $SERVICE_NAME"
echo "   2. Check logs to see tunnel URL: sudo journalctl -u $SERVICE_NAME -f"
echo "   3. Look for QR code on e-ink display (if available)"
echo ""
echo "The tunnel service will start automatically on boot and maintain"
echo "a persistent connection for remote access to your device."
