# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

Unified WiFi provisioning service for Raspberry Pi CM5 devices with E-ink display support. Single
async Python service using FastAPI, WebSocket, and persistent mDNS.

## Essential Commands

```bash
# Development (requires sudo for NetworkManager)
./dev.sh setup              # Install dependencies (prefers uv)
./dev.sh run                # Start with --no-hardware --debug
./dev.sh run --port 9090    # Custom port
./dev.sh status             # Check environment

# Linting & Testing
./lint.sh --check           # Comprehensive linting
./lint.sh --fix             # Auto-fix issues
uv run ruff check .         # Fast Python linting
uv run mypy --ignore-missing-imports --no-strict-optional .

# Build & Deploy
./build-deb.sh              # Build Debian package
sudo dpkg -i dist/*.deb     # Install package
sudo systemctl start distiller-wifi
sudo journalctl -u distiller-wifi -f
```

## Architecture

```
distiller_wifi.py           # Main orchestrator
core/
├── config.py              # Pydantic settings
├── device_config.py       # Device configuration
├── state.py               # Event-driven state machine
├── network_manager.py     # Async NetworkManager wrapper
└── mdns_service.py        # Zeroconf/mDNS

services/
├── web_server.py          # FastAPI + WebSocket
├── display_service.py     # E-ink display manager
└── tunnel_service.py      # Pinggy SSH tunnels

State Flow: INITIALIZING → SETUP_MODE → CONNECTING → CONNECTED
```

## Key Patterns

- **Single service**: All functionality in one async process
- **Type hints**: Full Pydantic typing throughout
- **Async I/O**: All operations use async/await
- **WebSocket**: Real-time updates without polling
- **State-driven**: Event callbacks on state transitions
- **Monochrome UI**: Pure black (#000000) and white (#FFFFFF) only
- **No emojis**: Clean professional code

## Testing & Development

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
```

## Configuration

- Environment variables: `DISTILLER_*` prefix
- Config file: `/etc/distiller/config.json` (production) or `./config.json` (dev)
- State persistence: `/var/lib/distiller/state.json`
- Service requires root for NetworkManager operations

## Testing & Quality Assurance

```bash
# Testing (when test files exist)
uv run pytest                    # Run all tests
uv run pytest tests/test_state.py    # Run specific test file
uv run pytest -v -s             # Verbose output with print statements
uv run pytest --cov=core --cov=services    # With coverage

# Quality checks
uv run ruff format .             # Auto-format code
uv run ruff check . --fix        # Fix linting issues
uv run mypy --ignore-missing-imports --no-strict-optional .
```

## Security & Input Validation

- **Input sanitization**: All user inputs (SSID, passwords) have validation patterns
- **Command injection prevention**: Dangerous shell characters are blocked
- **Session management**: Unique session tracking with automatic cleanup
- **Password security**: WPA/WPA2 length requirements (8-63 chars) enforced

## Important Notes

- **Tests**: No test files exist yet - use pytest when adding (see Testing section above)
- **Root required**: Service needs sudo for NetworkManager and system directories
- **Package manager**: Project prefers `uv` (10-100x faster than pip)
- **Python 3.11+**: Minimum Python version requirement
- **Event-driven**: State changes trigger callbacks across all services
- **WebSocket real-time**: All UI updates happen via WebSocket, no polling
