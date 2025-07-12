# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Distiller CM5 Services - Claude Development Guide

## Project Overview
Comprehensive WiFi setup and network management service for Raspberry Pi CM5-based Distiller devices. Provides automated WiFi configuration with web interface, e-ink display integration, mDNS discovery, and SSH tunnel access for remote management.

**Package Management:** Uses `uv` package manager for fast, reliable dependency resolution and virtual environment management. Dependencies are defined in `pyproject.toml` with fallback support for traditional `pip` + `requirements.txt`.

## Development Commands

### Package Management (Primary - uv)
```bash
# Create/activate virtual environment using uv
uv venv
source .venv/bin/activate

# Install dependencies
uv sync                    # Install from pyproject.toml
uv add <package>          # Add new dependency
uv remove <package>       # Remove dependency
```

### Package Management (Fallback - pip)
```bash
# If uv is not available
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Development Tools
```bash
# Code formatting and linting (dev dependencies in pyproject.toml)
uv run black .            # Code formatting
uv run isort .            # Import sorting  
uv run flake8 .           # Linting
uv run mypy .             # Type checking
uv run pytest            # Run tests

# Or with activated venv:
black .
isort . 
flake8 .
mypy .
pytest
```

### Building and Packaging
```bash
# Build Debian package (primary deployment method)
./build-deb.sh           # Build full package for arm64 + all architectures
./build-deb.sh -v 1.0.1-1 full  # Build with specific version
./build-deb.sh clean     # Clean build artifacts
./build-deb.sh deps      # Install build dependencies
./build-deb.sh check     # Run lintian package checks

# Manual installation scripts (legacy)
sudo bash install-service.sh          # Install WiFi service to /home/distiller
sudo bash install-tunnel-service.sh   # Install tunnel service
```

### Testing and Development
```bash
# Test services without hardware dependencies
.venv/bin/python distiller_wifi_service.py --no-eink --verbose
.venv/bin/python pinggy_tunnel_service.py --verbose

# Test e-ink display (requires distiller-cm5-sdk)
.venv/bin/python wifi_info_display.py --display

# Test display handoff detection (RP2040 -> RPi CM5)
sudo ./start-wifi-service.sh --no-eink --verbose

# Check systemd services
sudo systemctl status distiller-wifi
sudo systemctl status pinggy-tunnel
sudo journalctl -u distiller-wifi -f
```

## Core Architecture

### Service Architecture
The system operates as two coordinated systemd services:

**distiller-wifi.service** - Primary WiFi management service that:
- Manages state transitions: INITIALIZING → HOTSPOT_MODE → CONNECTING → CONNECTED
- Creates WiFi hotspot for initial device configuration
- Provides web interface for network selection and credentials
- Transitions to client mode when WiFi is configured
- Updates e-ink display for user feedback
- Coordinates with tunnel service via systemd dependencies

**pinggy-tunnel.service** - SSH tunnel service that:
- Waits for WiFi connectivity before starting
- Creates SSH tunnels via Pinggy service for remote access
- Updates e-ink display with tunnel QR codes and connection info
- Auto-restarts tunnels every 55 minutes for reliability

### Key Components

**DistillerWiFiService** (`distiller_wifi_service.py`)
- Main service orchestrator with Flask web interface
- Handles single-radio WiFi hardware limitations 
- Manages hotspot ↔ client mode transitions without race conditions
- Integrates with distiller-cm5-sdk for e-ink display updates

**WiFiManager** (`network/wifi_manager.py`)
- Low-level NetworkManager interface via nmcli commands
- Handles WiFi scanning, connection, hotspot creation/destruction
- Robust connection verification with multiple fallback methods
- Proper sudo privilege handling for network operations

**DeviceConfigManager** (`network/device_config.py`) 
- Generates unique device identities with random suffixes (e.g., distiller-a4b2)
- Manages mDNS/Avahi service advertisement and transitions
- Updates system configuration (/etc/hostname, /etc/hosts)
- JSON-based persistent device configuration

**NetworkUtils** (`network/network_utils.py`)
- Synchronous wrapper around async WiFiManager operations
- Status reporting for current WiFi state, IP address, signal strength
- Compatible interface for display integration

### Critical Patterns

**Single-Radio Hardware Handling**
- WiFi hotspot and client modes cannot coexist - service coordinates sequential transitions
- State machine prevents race conditions during mode switches
- Proper delays and verification ensure reliable transitions

**Privilege Management**
- Services run as 'distiller' user, not root, for security
- Network commands use sudo with careful command building
- Systemd service restrictions limit file system access

**Display Integration**
- Uses distiller-cm5-sdk for all hardware e-ink operations
- Dynamic display sizing via SDK rather than hardcoded dimensions
- Graceful fallbacks when display hardware unavailable (--no-eink mode)

## Development Guidelines

### Dependency Management
- **IMPORTANT:** Always use `uv` for Python dependencies and virtual environment management - never fallback to pip unless explicitly required
- Add new dependencies via `uv add <package>` to maintain pyproject.toml consistency
- Test installations work with both uv and pip fallback methods

### Service Development
- Test services with `--no-eink --verbose` flags for development without hardware
- Use proper systemd service patterns - avoid blocking operations in main threads
- Handle NetworkManager state changes gracefully with proper error recovery
- Always test hotspot ↔ client transitions thoroughly

### Hardware Integration
- distiller-cm5-sdk integration is optional - services must work without e-ink display
- **RP2040 → RPi CM5 E-ink Handoff**: Service includes retry logic and background initialization to handle display control transfer during boot
- Test display operations fail gracefully when SDK unavailable
- Use SDK hardware abstraction rather than direct GPIO/SPI access
- For hardware with RP2040 boot display control, use `distiller-wifi-with-handoff.service` for better timing

### Network Operations
- All nmcli operations must handle sudo privileges correctly
- Verify network state with multiple methods for reliability  
- Handle single-radio hardware limitations in state machine design
- Test on actual Raspberry Pi hardware for WiFi behavior validation

### Web Interface
- Flask routes should be stateless and thread-safe
- API endpoints must handle concurrent access during state transitions
- Always validate form inputs and handle network operation failures gracefully

## RP2040 + RPi CM5 E-ink Display Handoff

For hardware configurations with RP2040 + RPi CM5 on the same carrier board sharing an e-ink display:

### The Problem
- During boot, RP2040 initially controls the e-ink display (shows boot logo)
- RPi CM5 needs to take control after boot completion
- Service startup may occur before handoff is complete, causing display operations to fail
- Without retry logic, display remains unresponsive until service restart

### Solutions Implemented (Now Default)

**1. Retry Logic in Display Functions**
- `display_on_eink()` now includes retry logic with exponential backoff
- `get_eink_display_dimensions()` retries SDK connection attempts
- `wait_for_display_handoff()` function detects when display becomes available

**2. Background Display Initialization**
- Service starts background thread to detect display availability
- Display updates deferred until handoff completes
- Non-critical display updates skipped if display not ready

**3. Default Handoff-Aware Service**
- `distiller-wifi.service` now includes display handoff support by default
- Uses specialized startup script `start-wifi-service.sh`
- Waits for display handoff before starting service
- Longer timeout periods and better timing
- **No manual configuration needed** - works automatically for all hardware

### Usage
```bash
# Standard service now includes handoff support by default:
sudo systemctl start distiller-wifi
sudo systemctl enable distiller-wifi

# Test manually with startup script:
sudo ./start-wifi-service.sh --verbose

# Check service status:
sudo systemctl status distiller-wifi
sudo journalctl -u distiller-wifi -f
```

## Security Considerations
- Services run as root for hardware access and network operations
- Network operations and display handoff require elevated privileges
- System capabilities limited through systemd security settings
- Web interface only accessible via WiFi hotspot or local network
- SSH tunnels provide secure remote access without exposing services directly