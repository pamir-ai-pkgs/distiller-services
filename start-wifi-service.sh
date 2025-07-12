#!/bin/bash
# 
# Distiller WiFi Service Startup Script (Oneshot Mode) with E-ink Display Handoff Support
#
# This script handles the RP2040 -> RPi CM5 e-ink display handoff during boot
# by waiting for the display to become available before starting the oneshot service.
# The service will exit after successful WiFi connection.
#

set -e

# Configuration
SERVICE_DIR="/opt/distiller-cm5-services"
VENV_PATH="$SERVICE_DIR/.venv"
SERVICE_SCRIPT="$SERVICE_DIR/distiller_wifi_service.py"
LOG_FILE="/var/log/distiller-wifi-startup.log"
MAX_DISPLAY_WAIT=60  # Maximum time to wait for display handoff
CHECK_INTERVAL=3     # Time between display checks

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if running as root (required for network operations)
if [[ $EUID -ne 0 ]]; then
    log "ERROR: This script must be run as root for network operations"
    exit 1
fi

# Change to service directory
cd "$SERVICE_DIR" || {
    log "ERROR: Could not change to service directory: $SERVICE_DIR"
    exit 1
}

log "Starting Distiller WiFi Service (Oneshot Mode) with display handoff support"

# Wait for system to be ready
log "Waiting for system initialization to complete..."
sleep 10

# Test if distiller-cm5-sdk is available
if python3 -c "from distiller_cm5_sdk.hardware.eink import get_display_info; get_display_info()" 2>/dev/null; then
    log "E-ink display is already available (no handoff needed)"
else
    log "Waiting for RP2040 -> RPi CM5 e-ink display handoff..."
    
    # Wait for display to become available
    start_time=$(date +%s)
    display_ready=false
    
    while [[ $(($(date +%s) - start_time)) -lt $MAX_DISPLAY_WAIT ]]; do
        if python3 -c "from distiller_cm5_sdk.hardware.eink import get_display_info; get_display_info()" 2>/dev/null; then
            log "E-ink display handoff completed successfully"
            display_ready=true
            break
        fi
        
        log "Display not ready yet, waiting ${CHECK_INTERVAL}s..."
        sleep $CHECK_INTERVAL
    done
    
    if [[ "$display_ready" == "false" ]]; then
        log "WARNING: Display handoff timeout after ${MAX_DISPLAY_WAIT}s - proceeding anyway"
    fi
fi

# Additional delay to ensure handoff is stable
log "Allowing additional time for display stabilization..."
sleep 5

# Start the WiFi service (oneshot mode)
log "Starting Distiller WiFi Service (Oneshot Mode)..."

if [[ -f "$VENV_PATH/bin/python" ]]; then
    log "Using virtual environment: $VENV_PATH"
    exec "$VENV_PATH/bin/python" "$SERVICE_SCRIPT" "$@"
else
    log "Using system Python"
    exec python3 "$SERVICE_SCRIPT" "$@"
fi