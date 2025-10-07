# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Modern async WiFi provisioning service for Distiller devices (Raspberry Pi CM5, Radxa Zero 3/3W). Provides network configuration through access point mode, client mode, and secure tunnel access. Features e-ink display integration and web-based configuration interface.

**Project Type**: Python 3.11+ with uv package manager
**Architecture**: Async (asyncio) with event-driven state management
**Framework**: FastAPI + WebSocket + NetworkManager D-Bus
**Dependencies**: Requires distiller-sdk >= 3.0.0

## Core Architecture

### Service Orchestration (distiller_wifi.py:60-323)

Main application class `DistillerWiFiApp` orchestrates all services:
- StateManager: Event-driven state with persistence
- NetworkManager: WiFi operations via NetworkManager D-Bus
- WebServer: FastAPI web interface + WebSocket
- DisplayService: E-ink display updates
- TunnelService: Secure remote access (FRP/Pinggy)
- AvahiService: mDNS advertisement

All services run as async tasks coordinated by asyncio.gather(). State changes trigger cascading updates through registered callbacks.

### State Machine (core/state.py)

Six connection states:
- `AP_MODE`: Running access point for configuration
- `SWITCHING`: Transitioning between modes
- `CONNECTING`: Attempting WiFi connection
- `CONNECTED`: Successfully connected to network
- `FAILED`: Connection attempt failed
- `DISCONNECTED`: Manually disconnected

State transitions trigger callbacks to update display, web clients, and network configuration. State persists to `/var/lib/distiller/state.json` with event-driven updates.

### Network Management (core/network_manager.py)

Wraps NetworkManager via nmcli commands:
- AP mode: Creates shared connection with dnsmasq
- Client mode: Connects to existing networks
- Captive portal: Wildcard DNS via `/etc/NetworkManager/dnsmasq-shared.d/`
- Event monitoring: Async monitoring of NetworkManager events (currently stubbed at 626-642)

Critical: Always check `wifi_device` before operations. Service stops conflicting DNS services (dnsmasq) before starting AP mode (44-68).

### Web Server (services/web_server.py)

FastAPI application with three route groups:
1. **Captive portal routes** (92-148): OS connectivity checks (Android, iOS, Windows) redirect to setup page
2. **Web UI routes** (150+): HTML templates for user interface
3. **API routes**: `/api/networks`, `/api/connect`, `/api/status`, `/api/disconnect`
4. **WebSocket** (`/ws`): Real-time state updates to connected clients

Connection requests are async - client receives 202 Accepted, then monitors state via WebSocket.

### Display Service (services/display_service.py)

Event-driven e-ink updates (no polling):
- Registers state change callbacks
- Generates screens via display_screens.py component layouts
- Supports both hardcoded screens and TemplateRenderer templates
- Gracefully degrades when hardware unavailable
- Display operations: initialize → update → sleep → close

Display updates synchronized to prevent race conditions during rapid state changes.

## Development Commands

### Setup & Development
```bash
make setup                    # Install dependencies with uv
make run                      # Run with --no-hardware --debug (requires sudo)
make run ARGS="--port 9090"   # Custom arguments
```

### Code Quality
```bash
make lint                     # Run ruff, mypy, shellcheck
make fix                      # Auto-fix formatting issues
uv run ruff check .           # Lint only
uv run ruff format .          # Format only
uv run mypy --ignore-missing-imports . # Type check
```

### Building & Packaging
```bash
make build                    # Build Debian package (clean + build)
./build-deb.sh                # Build for arm64 (default)
./build-deb.sh native         # Build for current arch
TARGET_ARCH=amd64 ./build-deb.sh  # Override architecture
```

Package output: `dist/distiller-services_*.deb`

### Testing on Hardware
```bash
# Requires root for NetworkManager/hardware access
sudo uv run python distiller_wifi.py --no-hardware --debug

# With hardware (CM5/Radxa Zero 3)
sudo uv run python distiller_wifi.py --debug --port 8080

# Access web interface
# AP mode: http://192.168.42.1:8080
# Client mode: http://distiller-xxxx.local:8080
```

## Key Implementation Patterns

### Async Command Execution
All external commands use `_run_command()` helper (network_manager.py:117-131):
```python
returncode, stdout, stderr = await self._run_command(["nmcli", "..."])
```
Returns tuple of (returncode, stdout, stderr). Always check returncode before using output.

### State Updates with Callbacks
State changes trigger registered callbacks:
```python
# Register callback
state_manager.on_state_change(callback_function)

# Update state (triggers callbacks)
await state_manager.update_state(
    connection_state=ConnectionState.CONNECTED,
    network_info=NetworkInfo(ssid="...", ip_address="..."),
    reset_retry=True
)
```

### WebSocket Broadcasting
All state changes broadcast to connected WebSocket clients:
```python
await self._broadcast_status()  # Sends current state to all WebSocket connections
```

### Display Updates
Display service responds to state change callbacks (display_service.py:264-275):
```python
async def _on_state_change(self, old_state, new_state):
    logger.info(f"Display updating: {old_state} -> {new_state}")
    await self.update_display(new_state)
```

### AP Mode Password Management
Dynamic password generated per session (distiller_wifi.py:145-153):
```python
ap_password = generate_secure_password()  # 8 chars: letters + digits
await state_manager.update_state(ap_password=ap_password)
```
Password displayed on e-ink screen and logged to console.

### Captive Portal Configuration
Two-part system:
1. **Wildcard DNS** (network_manager.py:69-104): dnsmasq config makes all DNS queries return gateway IP
2. **Redirect routes** (web_server.py:92-148): OS connectivity checks return 302 redirects

Both required for automatic browser popup on mobile devices.

## Important Constraints

### Root Access Required
Most operations need root privileges:
- NetworkManager D-Bus operations
- Hardware access (GPIO, SPI for e-ink)
- System directory writes (`/var/lib/distiller`, `/etc/NetworkManager`)

Always check `os.geteuid() != 0` before starting (distiller_wifi.py:326-330).

### Hardware Detection
E-ink display initialization at services/display_service.py:75-100:
- Auto-detect via distiller-sdk platform detection
- Graceful degradation: saves debug PNG to `/tmp/` when hardware unavailable
- Display must initialize, update, sleep, close for each operation

### NetworkManager Dependencies
Service relies on NetworkManager's dnsmasq for AP mode:
- Stops conflicting dnsmasq service before starting
- Uses shared connection mode (not adhoc)
- Configures DNS via `/etc/NetworkManager/dnsmasq-shared.d/`

### State File Persistence
State saved to `/var/lib/distiller/state.json`:
- Survives restarts to reconnect to last network
- Contains tunnel URLs, retry counts, session tracking
- Cleared tunnel_url on restart (stale tunnel prevention at state.py:78-81)

## Common Development Tasks

### Adding a New Connection State
1. Add state to `ConnectionState` enum (core/state.py:18-26)
2. Create display screen function in `services/display_screens.py`
3. Add state handling in `DisplayService._on_state_change()`
4. Update WebSocket status response schema (services/web_server.py:54-60)

### Modifying Network Behavior
1. Edit `NetworkManager` methods (core/network_manager.py)
2. Update state transitions in `WebServer._connect_to_network()`
3. Test with `--no-hardware` flag first
4. Verify on actual hardware before packaging

### Adding API Endpoints
1. Add route in `WebServer._setup_routes()` (services/web_server.py)
2. Define Pydantic request/response models
3. Update OpenAPI docs (available at `/api/docs` when `debug=True`)
4. Broadcast state changes via WebSocket if needed

### Debugging Connection Issues
```bash
# Watch NetworkManager events
nmcli monitor

# Check active connections
nmcli connection show --active

# View service logs
sudo journalctl -u distiller-wifi -f

# Check state file
cat /var/lib/distiller/state.json

# Test DNS in AP mode
nslookup google.com 192.168.42.1

# Verify captive portal config
cat /etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf
```

## Known Issues & TODO

See TODO.md for detailed technical implementation plan addressing:
- Network connectivity validation (currently checks cached state only at network_manager.py:626)
- Event monitoring implementation (stubbed at network_manager.py:626-642)
- Connection request serialization
- AP password stability during retries
- Display update race conditions

## Testing Strategy

No automated test suite currently. Manual testing required for:
- AP mode → Client mode transitions
- Failed connection recovery
- Network loss detection
- E-ink display updates during state changes
- WebSocket real-time updates
- Captive portal detection on iOS/Android

Test with `--no-hardware --debug` flags for development without physical device.

## File Organization

```
distiller-services/
├── core/                    # Core business logic
│   ├── state.py            # State machine & persistence
│   ├── network_manager.py  # NetworkManager wrapper
│   ├── config.py           # Settings & environment
│   ├── device_config.py    # Device ID & hostname
│   ├── captive_portal.py   # Captive portal iptables (legacy)
│   └── avahi_service.py    # mDNS advertisement
├── services/               # Service implementations
│   ├── web_server.py       # FastAPI application
│   ├── display_service.py  # E-ink display updates
│   ├── display_screens.py  # Screen layouts
│   ├── display_layouts.py  # Layout components
│   ├── display_theme.py    # Design tokens
│   └── tunnel_service.py   # FRP/Pinggy tunnels
├── templates/              # Jinja2 HTML templates
├── static/                 # CSS, JS assets
├── debian/                 # Debian packaging files
├── distiller_wifi.py       # Main entry point
├── pyproject.toml          # Python project config
├── Makefile                # Development commands
└── build-deb.sh            # Universal Debian builder
```

## Deployment

Service installed as systemd unit at `/opt/distiller-services`:
```bash
sudo systemctl start distiller-wifi
sudo systemctl status distiller-wifi
sudo systemctl enable distiller-wifi  # Auto-start on boot
```

Logs: `/var/log/distiller/distiller-wifi.log` (rotating, 10MB limit)
State: `/var/lib/distiller/state.json`
Config: Environment variables or config file

## Version Information

Current version: 3.0.0 (see pyproject.toml:3)
Requires: distiller-sdk >= 3.0.0 (debian/control:27)
Replaces: distiller-cm5-services < 3.0.0 (debian/control:28-30)
