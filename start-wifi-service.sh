#!/bin/bash
# 
# Distiller WiFi Service Startup Script (Oneshot Mode)
#
# Simple startup script that runs the oneshot WiFi service.
# The service will exit after successful WiFi connection.
#

set -e

# Configuration
SERVICE_DIR="/opt/distiller-cm5-services"
SDK_DIR="/opt/distiller-cm5-sdk"
VENV_PATH="$SERVICE_DIR/.venv"
SDK_VENV_PATH="$SDK_DIR/.venv"
SERVICE_SCRIPT="$SERVICE_DIR/distiller_wifi_service.py"
LOG_FILE="/var/log/distiller-wifi-startup.log"

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

log "Starting Distiller WiFi Service (Oneshot Mode)"

# Set up SDK environment variables
export PYTHONPATH="/opt/distiller-cm5-sdk/src:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="/opt/distiller-cm5-sdk/lib:${LD_LIBRARY_PATH:-}"

# Wait for system to be ready
log "Waiting for system initialization to complete..."
sleep 10

# Start the WiFi service (oneshot mode)
log "Starting Distiller WiFi Service (Oneshot Mode)..."
log "SDK Environment: PYTHONPATH=$PYTHONPATH"
log "SDK Environment: LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

# Choose Python environment in order of preference
if [[ -f "$VENV_PATH/bin/python" ]]; then
    log "Using services virtual environment: $VENV_PATH"
    exec "$VENV_PATH/bin/python" "$SERVICE_SCRIPT" "$@"
elif [[ -f "$SDK_VENV_PATH/bin/python" ]]; then
    log "Using SDK virtual environment: $SDK_VENV_PATH"
    exec "$SDK_VENV_PATH/bin/python" "$SERVICE_SCRIPT" "$@"
else
    log "Using system Python"
    exec python3 "$SERVICE_SCRIPT" "$@"
fi