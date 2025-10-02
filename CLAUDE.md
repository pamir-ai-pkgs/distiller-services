# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

Unified WiFi provisioning service for Raspberry Pi CM5 devices with E-ink display support. Single
async Python service using FastAPI, WebSocket, and persistent mDNS with captive portal support.

## Essential Commands

```bash
# Development (Makefile)
make setup              # Install dependencies with uv
make run                # Start with --no-hardware --debug (requires sudo)
make run ARGS="--port 9090"  # Custom port
make lint               # Check code (ruff, mypy, shellcheck)
make fix                # Auto-fix formatting issues
make clean              # Clean temporary files
make build              # Build Debian package

# Direct Commands
sudo uv run python distiller_wifi.py --no-hardware --debug
uv run ruff check .         # Fast Python linting
uv run ruff format .        # Auto-format code
uv run mypy --ignore-missing-imports --no-strict-optional .

# Build & Deploy
./build-deb.sh              # Build Debian package for arm64 + all architectures
sudo dpkg -i dist/*.deb     # Install package
sudo systemctl start distiller-wifi
sudo journalctl -u distiller-wifi -f

# Debugging
sudo journalctl -u distiller-wifi | grep "AP PASSWORD"  # View current AP password
wscat -c ws://localhost:8080/ws                        # Test WebSocket connection
```

## Architecture

```text
distiller_wifi.py           # Main orchestrator
core/
├── config.py              # Pydantic settings
├── device_config.py       # Device configuration
├── state.py               # Event-driven state machine
├── network_manager.py     # Async NetworkManager wrapper
├── avahi_service.py       # Avahi mDNS registration
└── captive_portal.py      # Captive portal with iptables

services/
├── web_server.py          # FastAPI + WebSocket
├── display_service.py     # E-ink display manager
├── display_screens.py     # Display state renderers
└── tunnel_service.py      # Pinggy SSH tunnels

State Flow: INITIALIZING → SETUP_MODE → CONNECTING → CONNECTED
                   ↑            ↓            ↓
                   └────────────← FAILED ←────┘
```

## Key Patterns

- **Single service**: All functionality in one async process
- **Type hints**: Full Pydantic typing throughout
- **Async I/O**: All operations use async/await
- **WebSocket**: Real-time updates without polling
- **State-driven**: Event callbacks on state transitions
- **Monochrome UI**: Pure black (#000000) and white (#FFFFFF) only
- **No emojis**: Clean professional code
- **Captive Portal**: Automatic browser popup in AP mode via iptables redirect
- **Session Persistence**: User sessions maintained across network transitions

## Development & API Testing

```bash
# Run without hardware
sudo uv run python distiller_wifi.py --no-hardware --debug

# API testing
curl http://localhost:8080/api/status
curl -X POST http://localhost:8080/api/connect \
  -H "Content-Type: application/json" \
  -d '{"ssid": "MyNetwork", "password": "pass"}'

# WebSocket testing
wscat -c ws://localhost:8080/ws

# Generate E-ink display previews
uv run python generate_eink_previews.py
```

## Configuration

- Environment variables: `DISTILLER_*` prefix
- Config file: `/etc/distiller/config.json` (production) or `./config.json` (dev)
- State persistence: `/var/lib/distiller/state.json`
- Device config: `/var/lib/distiller/device_config.json` (persistent device ID)
- Service requires root for NetworkManager operations

## Quality Assurance

```bash
# Code quality checks
make lint                        # Run all linters (ruff, mypy, shellcheck)
make fix                         # Auto-fix formatting issues

# Manual checks
uv run ruff check .              # Fast linting (seconds)
uv run ruff format --check .     # Format check (seconds)
uv run mypy --ignore-missing-imports --no-strict-optional --exclude debian .

# Tests (Note: No test files exist yet)
make test                        # Run all tests
# When adding tests, use pytest:
# uv run pytest                               # Run all tests
# uv run pytest tests/test_state.py          # Run specific test file
# uv run pytest -k "test_connect"             # Run tests matching pattern
# uv run pytest -v -s                         # Verbose with print statements
# uv run pytest --cov=core --cov=services    # With coverage report
# uv run pytest --lf                          # Run only last failed tests
```

## Security & Input Validation

- **Input sanitization**: All user inputs (SSID, passwords) have validation patterns
- **Command injection prevention**: Dangerous shell characters are blocked
- **Session management**: Unique session tracking with automatic cleanup
- **Password security**: WPA/WPA2 length requirements (8-63 chars) enforced
- **Dynamic AP password**: New 12-char secure password generated on each startup

## Important Notes

- **Root required**: Service needs sudo for NetworkManager and system directories
- **Package manager**: Project prefers `uv` (10-100x faster than pip)
- **Python 3.11+**: Minimum Python version requirement
- **Event-driven**: State changes trigger callbacks across all services
- **WebSocket real-time**: All UI updates happen via WebSocket, no polling
- **Debian build**: Targets arm64 and all architectures for Raspberry Pi CM5
- **No test files yet**: Test infrastructure is configured but no tests written
- **Captive Portal**: Uses iptables for HTTP redirect in AP mode
- **Dynamic Password**: New AP password generated on each startup (check logs)
