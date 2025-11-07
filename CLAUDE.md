# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Distiller WiFi Provisioning Service is an async Python service for ARM64 edge devices (Raspberry Pi CM5, Radxa Zero 3/3W) that provides WiFi network configuration through access point mode, web interface, captive portal, e-ink display feedback, and remote access via FRP/Pinggy tunnels.

**Python:** 3.11+
**Package Manager:** `uv` (not pip or poetry)
**Architecture:** Event-driven async with state machine

## Development Environment

The codebase automatically detects development vs production environments via `src/distiller_services/paths.py`:

**Auto-Detection Logic:**
- Development: `templates/` and `static/` exist in project root (3 levels up from `paths.py`)
- Production: Installed to system paths (`/usr/lib/distiller-services/`)
- Detection is cached with `@lru_cache` for performance

**Path Resolution Priority (all paths):**
1. Environment variable override (highest priority)
2. Development paths (`./var/`, `./templates/`, etc.)
3. Production paths (`/var/lib/`, `/usr/share/`, etc.)

**Development Paths:**
- State: `./var/lib/distiller/`
- Logs: `./var/log/distiller/`
- Templates: `./templates/`
- Static files: `./static/`
- SDK: `../distiller-sdk/src/` (monorepo sibling)

**Production Paths:**
- State: `/var/lib/distiller/`
- Logs: `/var/log/distiller/`
- Templates: `/usr/share/distiller-services/templates/`
- Static files: `/usr/share/distiller-services/static/`
- SDK: `/opt/distiller-sdk/src/`

**Environment Variable Overrides:**
```bash
export DISTILLER_STATE_DIR=/tmp/distiller-state
export DISTILLER_LOG_DIR=/tmp/distiller-logs
export DISTILLER_TEMPLATES_DIR=/custom/templates
export DISTILLER_STATIC_DIR=/custom/static
export DISTILLER_SDK_PATH=/custom/sdk/src
export DISTILLER_DEVICE_ENV_PATH=/custom/device.env
```

## Common Commands

### Development Setup
```bash
uv sync                                    # Install dependencies
just setup                                 # Alias for uv sync
```

### Running Service
```bash
just run                                   # Run with --no-hardware --debug
just run ARGS="--port 9090"               # Run on custom port
sudo -E uv run python -m distiller_services --no-hardware --debug
sudo -E uv run python -m distiller_services --debug --port 9090  # Full control
```

**CLI Arguments:**
- `--config PATH` - Path to configuration file
- `--debug` - Enable debug logging (INFO -> DEBUG level)
- `--port PORT` - Web server port (default: 8080)
- `--no-hardware` - Bypass hardware checks for development

### Code Quality
```bash
just lint                                  # Run ruff check + format + mypy
just fix                                   # Auto-fix with ruff
uv run ruff check .                       # Linting only
uv run ruff format .                      # Formatting only
uv run mypy --ignore-missing-imports .    # Type checking only
```

### Building Package
```bash
just build                                 # Build Debian package (arm64)
just build amd64                          # Cross-build for amd64
just clean                                # Clean build artifacts
```

### Service Management
```bash
just status                                # Check service status
just logs                                  # View last 100 log lines
just logs follow                           # Follow logs in real-time
sudo systemctl restart distiller-wifi      # Restart service
sudo journalctl -u distiller-wifi -f      # Direct systemd logs
```

## Architecture

### Core Application Structure

```
DistillerWiFiApp (__main__.py)
├── StateManager (state.py)                # Event-driven state with file persistence
├── NetworkManager (network_manager.py)    # WiFi operations via NetworkManager D-Bus
├── WebServer (web_server.py)             # FastAPI + WebSocket
├── DisplayService (display_service.py)    # E-ink visual feedback
├── TunnelService (tunnel_service.py)      # FRP/Pinggy remote access
└── AvahiService (avahi_service.py)       # mDNS advertisement
```

### State Machine

Six connection states drive the entire system:
- `AP_MODE`: Running access point for configuration
- `SWITCHING`: Transitioning between network modes
- `CONNECTING`: Attempting WiFi connection
- `CONNECTED`: Successfully connected to network
- `FAILED`: Connection attempt failed
- `DISCONNECTED`: Manually disconnected

State transitions trigger callbacks that propagate updates to:
1. Display service (e-ink updates)
2. Web server (WebSocket broadcasts)
3. Tunnel service (start/stop tunnels)
4. State file (`/var/lib/distiller/state.json`)

### Event-Driven Flow

1. **State Changes**: StateManager triggers callbacks on state transitions
2. **Network Events**: NetworkManager monitors D-Bus and triggers callbacks
3. **Cascading Updates**: Each component reacts to events independently
4. **Async Coordination**: All I/O uses asyncio (no blocking operations)

### Connection Race Prevention

Application-level connection lock (`_connection_lock` in `__main__.py`) prevents concurrent connection attempts:
- Only ONE connection operation at a time (user-initiated or auto-recovery)
- `_connection_initiator` tracks whether connection is user-initiated or auto-recovery
- WebServer receives lock reference to coordinate with recovery logic
- Auto-recovery backs off if user connection is in progress
- Lock uses `acquire_nowait()` for non-blocking checks during recovery

### Key Design Patterns

**StateManager Callbacks:**
```python
self.state_manager.on_state_change(self._handle_state_change)
await self.state_manager.update_state(connection_state=ConnectionState.CONNECTED)
# Triggers all registered callbacks with old_state, new_state
```

**NetworkManager Events:**
```python
self.network_manager.on_network_event(self._handle_network_event)
# Monitors: connectivity_lost, device_disconnected, connectivity_restored
```

**WebSocket Broadcasting:**
State changes automatically broadcast to all connected WebSocket clients via `WebServer._broadcast_state()`.

**Display Updates:**
DisplayService runs in background loop, checking state every 2 seconds and updating e-ink display on changes.

**Tunnel Failover:**
TunnelService tries FRP first (if device has serial), falls back to Pinggy, monitors FRP health and switches back when available.

## Important Code Locations

### Entry Points
- `src/distiller_services/__main__.py` - Main application entry, orchestrates all services
- `debian/distiller-wifi` - Console script wrapper (installed to /usr/bin)
- `pyproject.toml` defines `distiller-wifi` entry point mapping to `__main__:main`

### Core Logic
- `paths.py` - Centralized path management, environment detection, path resolution
- `core/state.py` - State management, persistence, callbacks (SystemState, StateManager)
- `core/network_manager.py` - NetworkManager wrapper, WiFi operations
- `core/config.py` - Pydantic Settings with environment variable support
- `core/device_config.py` - Device ID generation from MAC address
- `core/captive_portal.py` - Captive portal DNS configuration
- `core/avahi_service.py` - mDNS service advertisement

### Services
- `services/web_server.py` - FastAPI app, REST endpoints, WebSocket, captive portal
- `services/display_service.py` - E-ink display service (uses distiller-sdk)
- `services/display_screens.py` - Screen rendering logic
- `services/display_layouts.py` - Layout components (QR codes, text, progress bars)
- `services/display_theme.py` - Display theming
- `services/tunnel_service.py` - FRP/Pinggy tunnel management

### Configuration
- `pyproject.toml` - Package metadata, dependencies, tool configs (ruff, mypy)
- `Justfile` - Development commands (build, run, lint, clean)
- `distiller-wifi.service` - Systemd service unit

### Debian Packaging
- `debian/control` - Package metadata, dependencies
- `debian/rules` - Custom build steps (installs to /usr/lib/distiller-services)
- `debian/postinst` - Post-install script (creates state dir, runs uv sync)
- `debian/preinst` - Pre-install script (stops service)
- `debian/postrm` - Post-removal script (cleanup)

## Critical Implementation Details

### Captive Portal
Uses NetworkManager's dnsmasq with wildcard DNS (`address=/#/192.168.4.1`) to trigger captive portal popups on Android, iOS, Windows. Configuration in `/etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf`.

### Network Profile Validation
`_validate_network_profile()` checks file ownership (root) and permissions (0600) before using existing profiles.

### State Persistence
StateManager saves to `/var/lib/distiller/state.json` on every update using atomic writes (temp file + rename). Datetime objects converted to ISO format for JSON serialization.

### Tunnel Provider Priority
1. Try FRP first if device has serial from `/etc/pamir/device.env`
2. Fall back to Pinggy (free or persistent with token)
3. Monitor FRP health every 60s and switch back when available
4. Refresh Pinggy tunnels before expiry (55min free, 24h persistent)

### Display Update Throttling
DisplayService checks state every 2 seconds but only updates e-ink display if state changed. Uses distiller-sdk's `display.clear()` and `display.display(image)`.

### Network Recovery
On connection loss, system executes `_recover_from_network_loss()`:
1. Checks if connection lock is held (user operation in progress)
2. Uses non-blocking `acquire_nowait()` to prevent blocking user operations
3. Waits 3 seconds for transient issues to resolve
4. Attempts reconnection to saved network via `reconnect_to_saved_network()`
5. Verifies connectivity with active check before updating state
6. Falls back to AP mode via `_fallback_to_ap_mode()` on failure
7. Regenerates AP password each time AP mode is entered

**Recovery Coordination:**
- Auto-recovery defers to user-initiated connections
- Lock prevents simultaneous connection attempts
- Recovery triggered by NetworkManager D-Bus events: `connectivity_lost`, `device_disconnected`, `connection_deactivated`

### Root Requirement
Service requires root for:
- NetworkManager D-Bus operations (create/modify connections)
- Hardware access (SPI for e-ink display via distiller-sdk)
- System file writes (`/var/lib/distiller`, `/etc/NetworkManager`)
- iptables rules (captive portal)

## Code Style

- **Line Length**: 100 characters (ruff enforced)
- **Type Hints**: Required for function signatures
- **Async/Await**: All I/O operations (no blocking)
- **Import Order**: Ruff with isort profile (stdlib, third-party, local)
- **Docstrings**: Only for complex/non-obvious functions
- **Error Handling**: Specific exceptions, log with context
- **Logging Levels**: DEBUG for frequent events, INFO for state changes, WARNING for failures

## Testing

### Development Mode Testing
No installation required - run directly from source:
```bash
# Creates ./var/lib/distiller and ./var/log/distiller automatically
sudo -E uv run python -m distiller_services --no-hardware --debug
```

The `-E` flag preserves environment variables for custom path overrides.

### Hardware-Independent Testing
Use `--no-hardware` flag to bypass display/hardware checks:
```bash
sudo uv run python -m distiller_services --no-hardware --debug
```

### Network Operations
Test network operations require:
- NetworkManager running
- WiFi device available
- Root privileges

### Captive Portal Testing
1. Start service in AP mode
2. Connect to `Distiller-XXXX` network
3. Android/iOS should auto-open browser to `http://192.168.4.1:8080`
4. Check DNS: `nslookup google.com 192.168.4.1` should return `192.168.4.1`

## Common Pitfalls

1. **Package Manager**: Must use `uv`, not `pip install` or `poetry`. All deps in pyproject.toml.
2. **Root Permissions**: Service requires root. Development also needs `sudo -E` to preserve environment.
3. **State File**: Development: `./var/lib/distiller/state.json`. Production: `/var/lib/distiller/state.json`.
4. **Development Auto-Detection**: Checks for `templates/` and `static/` in project root. Missing these triggers production mode.
5. **Captive Portal**: Requires NetworkManager restart after config changes. Use `sudo systemctl restart NetworkManager`.
6. **Display**: Requires distiller-sdk >= 3.0.0. Development looks for `../distiller-sdk/src/` (monorepo).
7. **AP Password**: Dynamically generated on each AP mode entry. Check logs or state file for current password.
8. **Tunnel URLs**: FRP requires device serial. Development won't have `/etc/pamir/device.env`, only Pinggy works.
9. **NetworkManager Profiles**: Stored in `/etc/NetworkManager/system-connections/` with 0600 permissions.

## Debugging

### Check State
```bash
# Development
cat ./var/lib/distiller/state.json | jq

# Production
cat /var/lib/distiller/state.json | jq
```

### Check NetworkManager
```bash
nmcli device status
nmcli connection show
nmcli device wifi list
nmcli connection show --active
```

### Check Captive Portal
```bash
cat /etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf
nslookup google.com 192.168.4.1
sudo iptables -t nat -L -n -v
```

### Check Display
```bash
# Development
grep -i display ./var/lib/distiller/state.json
ls -la ../distiller-sdk/src/  # Monorepo sibling

# Production
grep -i display /var/lib/distiller/state.json
ls -la /dev/spidev*
ls -la /opt/distiller-sdk/
```

### Check Tunnel
```bash
sudo journalctl -u distiller-wifi | grep -i tunnel
sudo systemctl status frpc.service
cat /etc/pamir/device.env
```

## File Locations

### Development (Project Root)

| Path | Purpose |
|------|---------|
| `./templates/` | Jinja2 templates |
| `./static/` | CSS/JS/images |
| `./var/lib/distiller/state.json` | Persistent state |
| `./var/lib/distiller/device_config.json` | Device identity |
| `./var/log/distiller/distiller-wifi.log` | Rotating logs (10MB × 3) |
| `../distiller-sdk/src/` | SDK source (monorepo sibling) |

### Production (Installed System)

| Path | Purpose |
|------|---------|
| `/usr/lib/distiller-services/` | Installed package code |
| `/usr/lib/distiller-services/src/distiller_services/` | Python source |
| `/usr/lib/distiller-services/.venv/` | uv-managed virtual environment |
| `/usr/share/distiller-services/templates/` | Jinja2 templates |
| `/usr/share/distiller-services/static/` | CSS/JS/images |
| `/usr/bin/distiller-wifi` | Console script wrapper |
| `/var/lib/distiller/state.json` | Persistent state |
| `/var/lib/distiller/device_config.json` | Device identity |
| `/etc/pamir/device.env` | Device serial (if exists) |
| `/etc/NetworkManager/system-connections/` | WiFi profiles |
| `/etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf` | Captive portal DNS |
| `/var/log/distiller/distiller-wifi.log` | Rotating logs (10MB × 3) |
| `/lib/systemd/system/distiller-wifi.service` | Systemd unit |

## Dependencies

**Runtime:** distiller-sdk >= 3.0.0, python3 >= 3.11, uv, systemd, network-manager, dnsmasq, avahi-daemon, iptables, openssh-client

**Python:** fastapi, uvicorn[standard], pydantic, httpx, jinja2, pillow, qrcode[pil], websockets

**Dev:** pytest, pytest-asyncio, ruff, mypy, djlint, yamllint
