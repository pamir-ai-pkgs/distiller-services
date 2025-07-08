#!/bin/bash

# Distiller CM5 Services Installation Script
# Installs WiFi setup service and supporting files as systemd services
# Updated for current project structure and dependencies

set -e

# Configuration
SERVICE_NAME="distiller-wifi"
SERVICE_FILE="distiller-wifi.service"
SERVICE_USER="root"
INSTALL_DIR="/opt/distiller-cm5-services"
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================"
echo "Distiller CM5 Services Installation Script"
echo "Installing WiFi setup service and supporting components..."
echo "================================================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
	echo "Error: This script must be run as root"
	echo "Please run: sudo bash install-service.sh"
	exit 1
fi

# Detect system information
echo "Detecting system information..."
if [ -f /etc/os-release ]; then
	. /etc/os-release
	echo "   OS: $PRETTY_NAME"
	echo "   Architecture: $(uname -m)"
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update -qq
apt-get install -y \
	avahi-daemon \
	avahi-utils \
	libnss-mdns \
	python3 \
	python3-pip \
	python3-venv \
	systemd \
	wireless-tools \
	wpasupplicant \
	hostapd \
	dnsmasq \
	iptables \
	netplan.io || true

# Create installation directory
echo "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy service files with proper structure
echo "Copying service files..."
cp "$CURRENT_DIR/distiller_wifi_service.py" "$INSTALL_DIR/"
cp "$CURRENT_DIR/eink_display_flush.py" "$INSTALL_DIR/"
cp "$CURRENT_DIR/wifi_info_display.py" "$INSTALL_DIR/"
cp "$CURRENT_DIR/pinggy_tunnel_service.py" "$INSTALL_DIR/"
cp "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"

# Copy directories
cp -r "$CURRENT_DIR/network" "$INSTALL_DIR/"
cp -r "$CURRENT_DIR/templates" "$INSTALL_DIR/"
cp -r "$CURRENT_DIR/static" "$INSTALL_DIR/"

# Copy fonts if they exist
if [ -d "$CURRENT_DIR/fonts" ]; then
	cp -r "$CURRENT_DIR/fonts" "$INSTALL_DIR/"
fi

# Set permissions
echo "Setting permissions..."
chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/distiller_wifi_service.py"
chmod +x "$INSTALL_DIR/eink_display_flush.py"
chmod +x "$INSTALL_DIR/wifi_info_display.py"
chmod +x "$INSTALL_DIR/pinggy_tunnel_service.py"

# Create Python virtual environment for better isolation
echo "Setting up Python environment..."
VENV_DIR="$INSTALL_DIR/venv"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install Python dependencies
echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Update service file to use virtual environment
echo "Configuring systemd service..."
if [ -f "$SERVICE_FILE" ]; then
	# Create updated service file
	cat >"$SYSTEMD_DIR/$SERVICE_FILE" <<EOF
[Unit]
Description=Distiller CM5 WiFi Setup Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$VENV_DIR/bin
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/distiller_wifi_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
else
	echo "Error: $SERVICE_FILE not found in current directory"
	echo "Expected files:"
	echo "  - distiller-wifi.service"
	echo "  - distiller_wifi_service.py"
	echo "  - network/ directory"
	echo "  - templates/ directory"
	echo "  - static/ directory"
	exit 1
fi

# Set proper permissions for service file
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

# Configure Avahi daemon for mDNS
echo "Configuring Avahi daemon for mDNS..."
systemctl enable avahi-daemon
systemctl start avahi-daemon

# Configure hostname resolution
echo "Configuring hostname resolution..."
if ! grep -q "distiller.local" /etc/hosts; then
	echo "127.0.1.1 distiller.local" >>/etc/hosts
fi

# Reload systemd and enable service
echo "Configuring systemd service..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# Create a simple status check script
echo "Creating status check script..."
cat >"$INSTALL_DIR/check-status.sh" <<'EOF'
#!/bin/bash
echo "=== Distiller CM5 Services Status ==="
echo "WiFi Service Status:"
systemctl status distiller-wifi --no-pager -l
echo ""
echo "Service Logs (last 10 lines):"
journalctl -u distiller-wifi -n 10 --no-pager
echo ""
echo "Network Interfaces:"
ip addr show | grep -E "^[0-9]|inet "
echo ""
echo "WiFi Networks:"
nmcli dev wifi list 2>/dev/null || iwlist scan 2>/dev/null | grep ESSID || echo "WiFi scan not available"
EOF

chmod +x "$INSTALL_DIR/check-status.sh"

# Create an uninstall script
echo "Creating uninstall script..."
cat >"$INSTALL_DIR/uninstall.sh" <<EOF
#!/bin/bash
echo "Uninstalling Distiller CM5 Services..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl disable $SERVICE_NAME 2>/dev/null || true
rm -f "$SYSTEMD_DIR/$SERVICE_FILE"
systemctl daemon-reload
echo "Service uninstalled. Installation directory $INSTALL_DIR preserved."
echo "To remove completely: sudo rm -rf $INSTALL_DIR"
EOF

chmod +x "$INSTALL_DIR/uninstall.sh"

echo ""
echo "Installation complete!"
echo ""
echo "Service Information:"
echo "   Service Name: $SERVICE_NAME"
echo "   Install Directory: $INSTALL_DIR"
echo "   Python Environment: $VENV_DIR"
echo ""
echo "Quick Start Commands:"
echo "   Start service:     sudo systemctl start $SERVICE_NAME"
echo "   Stop service:      sudo systemctl stop $SERVICE_NAME"
echo "   Check status:      sudo systemctl status $SERVICE_NAME"
echo "   View logs:         sudo journalctl -u $SERVICE_NAME -f"
echo "   Check everything:  sudo $INSTALL_DIR/check-status.sh"
echo ""
echo "Management:"
echo "   Uninstall:         sudo $INSTALL_DIR/uninstall.sh"
echo ""
echo "Access:"
echo "   WiFi Setup:        http://distiller.local (when in setup mode)"
echo "   Direct IP:         http://[device-ip]:3000"
echo ""
echo "The service will start automatically on boot."
echo "The device will broadcast a setup hotspot when not connected to WiFi."
