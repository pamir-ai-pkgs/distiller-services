#!/bin/bash

# Distiller Services Installation Script
# Based on Debian packaging for manual installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/distiller-services"
SERVICE_NAME="distiller-wifi"
SYSTEMD_PATH="/lib/systemd/system"
VAR_DIR="/var/lib/distiller"
LOG_DIR="/var/log/distiller"

# Print colored output
print_color() {
    echo -e "${2}${1}${NC}"
}

print_info() {
    print_color "→ $1" "$BLUE"
}

print_success() {
    print_color "✓ $1" "$GREEN"
}

print_warning() {
    print_color "⚠ $1" "$YELLOW"
}

print_error() {
    print_color "✗ $1" "$RED"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root or with sudo"
        exit 1
    fi
}

# Detect architecture
detect_arch() {
    ARCH=$(uname -m)
    case "$ARCH" in
        aarch64|arm64)
            print_info "Detected ARM64 architecture (Raspberry Pi CM5 compatible)"
            ;;
        x86_64|amd64)
            print_info "Detected x86_64 architecture"
            ;;
        *)
            print_warning "Unknown architecture: $ARCH"
            ;;
    esac
}

# Check Python version
check_python() {
    print_info "Checking Python version..."
    
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11 ]]; then
        print_error "Python 3.11 or higher is required (found: $PYTHON_VERSION)"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
}

# Install system dependencies
install_dependencies() {
    print_info "Checking system dependencies..."
    
    # Update PATH for uv
    export PATH="/root/.local/bin:/root/.cargo/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
    
    # Check for package manager
    if command -v apt-get >/dev/null 2>&1; then
        PKG_MANAGER="apt-get"
    elif command -v dnf >/dev/null 2>&1; then
        PKG_MANAGER="dnf"
    elif command -v yum >/dev/null 2>&1; then
        PKG_MANAGER="yum"
    else
        print_error "No supported package manager found (apt, dnf, yum)"
        exit 1
    fi
    
    # Check which packages need to be installed
    PACKAGES="python3-dev python3-venv systemd network-manager avahi-daemon openssh-client curl wget"
    MISSING_PACKAGES=""
    
    if [[ "$PKG_MANAGER" == "apt-get" ]]; then
        for pkg in $PACKAGES; do
            if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
                MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
            fi
        done
    else
        for pkg in $PACKAGES; do
            if ! rpm -q "$pkg" >/dev/null 2>&1; then
                MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
            fi
        done
    fi
    
    if [[ -n "$MISSING_PACKAGES" ]]; then
        print_info "Installing missing packages:$MISSING_PACKAGES"
        
        if [[ "$PKG_MANAGER" == "apt-get" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -qq
            # shellcheck disable=SC2086
            apt-get install -y -qq --no-install-recommends $MISSING_PACKAGES
        else
            # shellcheck disable=SC2086
            $PKG_MANAGER install -y $MISSING_PACKAGES
        fi
        
        print_success "System dependencies installed"
    else
        print_success "All system dependencies already installed"
    fi
}

# Install uv package manager
install_uv() {
    print_info "Checking for uv package manager..."
    
    export PATH="/root/.local/bin:/root/.cargo/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
    
    if ! command -v uv >/dev/null 2>&1; then
        print_info "Installing uv package manager..."
        
        TEMP_DIR=$(mktemp -d)
        trap 'rm -rf '"$TEMP_DIR" EXIT
        
        if curl -LsSf https://astral.sh/uv/install.sh -o "$TEMP_DIR/install.sh" 2>/dev/null || \
           wget -q https://astral.sh/uv/install.sh -O "$TEMP_DIR/install.sh" 2>/dev/null; then
            
            if sh "$TEMP_DIR/install.sh" >/dev/null 2>&1; then
                # Check again after installation
                export PATH="/root/.local/bin:/root/.cargo/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
                
                if ! command -v uv >/dev/null 2>&1; then
                    print_warning "uv installed but not in PATH, trying to locate..."
                    
                    # Try to find uv in common locations
                    for path in /root/.cargo/bin /root/.local/bin $HOME/.cargo/bin $HOME/.local/bin; do
                        if [[ -f "$path/uv" ]]; then
                            export PATH="$path:$PATH"
                            print_success "Found uv at $path"
                            break
                        fi
                    done
                fi
            else
                print_error "Failed to install uv package manager"
                print_info "Please install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
                exit 1
            fi
        else
            print_error "Failed to download uv installer"
            print_info "Please install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    else
        print_success "uv package manager found"
    fi
}

# Create system directories
create_directories() {
    print_info "Creating system directories..."
    
    install -d -o root -g root -m 755 "$VAR_DIR"
    install -d -o root -g root -m 755 "$LOG_DIR"
    install -d -o root -g root -m 755 "$INSTALL_DIR"
    
    print_success "System directories created"
}

# Copy application files
copy_files() {
    print_info "Copying application files..."
    
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Ensure source files exist
    if [[ ! -f "$SCRIPT_DIR/distiller_wifi.py" ]]; then
        print_error "Source files not found in $SCRIPT_DIR"
        exit 1
    fi
    
    # Copy main application
    cp -f "$SCRIPT_DIR/distiller_wifi.py" "$INSTALL_DIR/"
    
    # Copy core modules
    if [[ -d "$SCRIPT_DIR/core" ]]; then
        cp -rf "$SCRIPT_DIR/core" "$INSTALL_DIR/"
    fi
    
    # Copy service modules
    if [[ -d "$SCRIPT_DIR/services" ]]; then
        cp -rf "$SCRIPT_DIR/services" "$INSTALL_DIR/"
    fi
    
    # Copy templates
    if [[ -d "$SCRIPT_DIR/templates" ]]; then
        cp -rf "$SCRIPT_DIR/templates" "$INSTALL_DIR/"
    fi
    
    # Copy static files
    if [[ -d "$SCRIPT_DIR/static" ]]; then
        cp -rf "$SCRIPT_DIR/static" "$INSTALL_DIR/"
    fi
    
    # Copy fonts if they exist
    if [[ -d "$SCRIPT_DIR/fonts" ]]; then
        cp -rf "$SCRIPT_DIR/fonts" "$INSTALL_DIR/"
    fi
    
    # Copy python requirements
    if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        cp -f "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/"
    fi
    
    print_success "Application files copied"
}

# Setup Python virtual environment
setup_venv() {
    print_info "Setting up Python virtual environment..."
    
    cd "$INSTALL_DIR"
    
    # Remove existing venv if present
    [[ -d ".venv" ]] && rm -rf ".venv"
    
    # Create new virtual environment
    print_info "Creating virtual environment..."
    uv venv --system-site-packages 2>/dev/null || uv venv
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    uv sync
    
    # Install SDK if available
    if [[ -d "/opt/distiller-sdk" ]]; then
        print_info "Installing Distiller SDK..."
        uv pip install -e /opt/distiller-sdk 2>/dev/null || true
    fi
    
    print_success "Virtual environment setup complete"
}

# Set permissions
set_permissions() {
    print_info "Setting file permissions..."
    
    # Set permissions on directories and Python files
    find "$INSTALL_DIR" -type d -exec chmod 755 {} \; \
        -o -type f -name "*.py" -exec chmod 755 {} \;
    
    # Make main script executable
    chmod +x "$INSTALL_DIR/distiller_wifi.py"
    
    print_success "Permissions set"
}

# Install systemd service
install_service() {
    print_info "Installing systemd service..."
    
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    VENV_PATH="$INSTALL_DIR/.venv"
    
    # Create service file
    cat > "$SYSTEMD_PATH/$SERVICE_NAME.service" << EOF
[Unit]
Description=Distiller WiFi Provisioning System
Documentation=https://github.com/pamir-ai/distiller-services
After=network-pre.target NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_PATH/bin/python $INSTALL_DIR/distiller_wifi.py
Restart=always
RestartSec=10
TimeoutStartSec=30
TimeoutStopSec=15

# Environment
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$INSTALL_DIR:/opt/distiller-sdk:/opt/distiller-sdk/src
Environment=LD_LIBRARY_PATH=/opt/distiller-sdk/lib

# Security settings - relaxed for network operations
NoNewPrivileges=false
ProtectSystem=false
ReadWritePaths=$VAR_DIR /etc/NetworkManager/system-connections /etc/hostname /etc/hosts /etc/avahi
SupplementaryGroups=netdev

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service
    systemctl enable "$SERVICE_NAME.service" 2>/dev/null || true
    
    print_success "Systemd service installed"
}

# Uninstall function
uninstall() {
    print_info "Starting uninstallation..."
    
    # Stop and disable service
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Stopping $SERVICE_NAME service..."
        systemctl stop "$SERVICE_NAME"
    fi
    
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        print_info "Disabling $SERVICE_NAME service..."
        systemctl disable "$SERVICE_NAME"
    fi
    
    # Remove service file
    if [[ -f "$SYSTEMD_PATH/$SERVICE_NAME.service" ]]; then
        print_info "Removing systemd service..."
        rm -f "$SYSTEMD_PATH/$SERVICE_NAME.service"
        systemctl daemon-reload
    fi
    
    # Remove application directory
    if [[ -d "$INSTALL_DIR" ]]; then
        print_info "Removing application files..."
        rm -rf "$INSTALL_DIR"
    fi
    
    # Remove system directories (with confirmation)
    read -p "Remove system directories ($VAR_DIR and $LOG_DIR)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VAR_DIR" "$LOG_DIR"
        print_success "System directories removed"
    fi
    
    # Remove NetworkManager connections
    if command -v nmcli >/dev/null 2>&1; then
        print_info "Removing Distiller NetworkManager connections..."
        nmcli connection show 2>/dev/null | grep -E "^Distiller-" | awk '{print $1}' | \
            xargs -r nmcli connection delete 2>/dev/null || true
    fi
    
    print_success "Uninstallation complete"
}

# Main installation function
install() {
    print_info "Starting Distiller CM5 Services installation..."
    
    check_root
    detect_arch
    check_python
    install_dependencies
    install_uv
    create_directories
    copy_files
    setup_venv
    set_permissions
    install_service
    
    print_success "Installation complete!"
    echo
    print_info "To start the service:"
    echo "  systemctl start $SERVICE_NAME"
    echo
    print_info "To check service status:"
    echo "  systemctl status $SERVICE_NAME"
    echo
    print_info "To view logs:"
    echo "  journalctl -u $SERVICE_NAME -f"
    echo
    print_info "Web interface will be available at:"
    echo "  http://localhost:8080"
    echo "  http://distiller.local:8080 (via mDNS)"
}

# Parse command line arguments
case "${1:-install}" in
    install)
        install
        ;;
    uninstall|remove)
        uninstall
        ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        echo
        echo "  install    - Install Distiller CM5 Services (default)"
        echo "  uninstall  - Remove Distiller CM5 Services"
        echo
        exit 1
        ;;
esac
