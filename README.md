# Distiller WiFi Provisioning Service

Modern asynchronous WiFi provisioning system for Distiller edge computing devices, providing secure network configuration through access point mode, client connectivity, and remote access via encrypted tunnels.

## Overview

Distiller WiFi Provisioning Service is a production-ready network configuration system designed for ARM-based embedded devices. The service orchestrates multiple subsystems to provide seamless WiFi setup through a web-based interface, automatic service discovery via mDNS, visual feedback through e-ink displays, and secure remote access through dual tunnel mechanisms.

**Version:** 3.0.0
**Target Platforms:** Raspberry Pi CM5, Radxa Zero 3, Radxa Zero 3W
**Architecture:** ARM64 Linux

### Key Capabilities

The service operates in two primary modes: Access Point (AP) mode for initial configuration and Client mode for normal operation. During AP mode, the device creates a temporary WiFi network with captive portal support, allowing users to configure WiFi credentials through any web browser. Once configured, the device transitions to Client mode, connecting to the specified network while maintaining remote access through FRP or Pinggy tunnels.

## Features

### Network Management

- **Access Point Mode**: Creates a temporary WiFi hotspot with dynamically generated secure passwords
- **Client Mode**: Connects to existing WiFi networks with automatic reconnection on failure
- **Network Scanning**: Real-time WiFi network discovery with signal strength indicators
- **Captive Portal**: Multi-OS automatic browser popup (Android, iOS, Windows, Firefox, Kindle)
- **State Persistence**: Network credentials survive reboots and power cycles

### Remote Access

- **Dual Tunnel System**: FRP (Fast Reverse Proxy) as primary, Pinggy SSH tunnel as fallback
- **Automatic Failover**: Monitors FRP health and switches providers on failure
- **Auto-Recovery**: Returns to FRP when service becomes available
- **Persistent Tunnels**: Support for Pinggy access tokens for 24-hour tunnel stability
- **URL Management**: Automatic tunnel URL extraction and state updates

### Device Identity

- **MAC-based Device ID**: 4-character identifier derived from hardware MAC address
- **Persistent Hostname**: Automatic system hostname configuration (distiller-xxxx)
- **Consistent SSID**: AP SSID remains stable across reboots (Distiller-XXXX)
- **mDNS Advertisement**: Avahi service discovery at distiller-xxxx.local

### Display Integration

- **E-ink Display Support**: Event-driven updates for 128x250 and 240x416 pixel displays
- **Component-based Layouts**: Modular screen design with theme system
- **QR Code Generation**: Quick access codes for setup URL and tunnel URLs
- **Connection Progress**: Real-time visual feedback during network transitions
- **Graceful Degradation**: Functions without display hardware in debug mode

### Web Interface

- **Responsive UI**: Mobile-optimized interface with monochrome aesthetic
- **Network Selection**: Visual network list with security badges and signal strength
- **Hidden Network Support**: Manual SSID entry for non-broadcast networks
- **Real-time Updates**: WebSocket-based state synchronization
- **Connection Status**: Live dashboard with network information and tunnel URLs

### Security

- **Input Validation**: Regex-based validation against command injection
- **Secure Password Generation**: Cryptographically secure random passwords
- **Atomic Operations**: Race condition prevention in file operations
- **Symlink Attack Prevention**: Temp file security validation
- **Restricted Permissions**: Systemd-based permission isolation

## System Architecture

### Component Overview

The service is built on an event-driven architecture where state changes trigger cascading updates across all subsystems:

```
DistillerWiFiApp
├── StateManager (Event-driven state with persistence)
├── NetworkManager (WiFi operations via NetworkManager D-Bus)
├── WebServer (FastAPI + WebSocket)
├── DisplayService (E-ink visual feedback)
├── TunnelService (FRP/Pinggy remote access)
└── AvahiService (mDNS advertisement)
```

### State Machine

The system operates through six distinct connection states:

1. **AP_MODE**: Running access point for configuration
2. **SWITCHING**: Transitioning between network modes
3. **CONNECTING**: Attempting WiFi connection
4. **CONNECTED**: Successfully connected to network
5. **FAILED**: Connection attempt failed
6. **DISCONNECTED**: Manually disconnected

State transitions trigger registered callbacks, updating the display, broadcasting to WebSocket clients, and adjusting network configuration.

### Network Topology

**Access Point Mode:**
```
Device (192.168.4.1/24) ← WiFi ← Client Devices
         ↓
    dnsmasq (DHCP + wildcard DNS)
         ↓
    Web Server (Port 8080)
```

**Client Mode:**
```
Device ← WiFi ← Router ← Internet
  ↓
  ├─ mDNS (distiller-xxxx.local)
  └─ Tunnel (FRP/Pinggy)
         ↓
    Public URL
```

### Service Orchestration

All services run as async tasks coordinated by `asyncio.gather()`. The main application manages lifecycle:

```python
tasks = [
    run_web_server(),      # FastAPI HTTP/WebSocket
    display_service.run(), # E-ink updates
    tunnel_service.run(),  # Remote access
    run_session_cleanup(), # Session management
    run_network_monitor()  # NetworkManager events
]
```

## Requirements

### Hardware

- **Supported Platforms**: Raspberry Pi CM5, Radxa Zero 3, Radxa Zero 3W
- **CPU Architecture**: ARM64 (aarch64)
- **Memory**: Minimum 512MB RAM (1GB recommended)
- **Storage**: Minimum 2GB available space
- **Network**: WiFi adapter (integrated or USB)
- **Display** (optional): E-ink display (EPD128x250 or EPD240x416)

### Software Dependencies

**System Packages:**
- Python 3.11 or higher
- systemd
- NetworkManager
- dnsmasq
- avahi-daemon
- avahi-utils
- iptables
- openssh-client

**Python Packages:**
- distiller-sdk >= 3.0.0
- fastapi >= 0.109.2
- uvicorn[standard] >= 0.27.1
- pydantic >= 2.6.1
- pydantic-settings >= 2.1.0
- httpx >= 0.25.0
- jinja2 >= 3.1.3
- pillow >= 10.2.0
- qrcode[pil] >= 7.4.2
- websockets >= 12.0
- python-multipart >= 0.0.9

## Installation

### Debian Package Installation

The recommended installation method for production deployments:

```bash
# Install Distiller SDK first (required dependency)
sudo dpkg -i distiller-sdk_3.0.0_arm64.deb

# Install WiFi provisioning service
sudo dpkg -i distiller-services_3.0.0_arm64.deb

# Enable and start service
sudo systemctl enable distiller-wifi.service
sudo systemctl start distiller-wifi.service

# Verify service status
sudo systemctl status distiller-wifi.service
```

The installation process:
1. Removes old 2.x installations if present
2. Configures MAC-based hostname
3. Creates virtual environment with uv
4. Installs Python dependencies
5. Installs distiller-sdk integration
6. Configures systemd service

### From Source Installation

For development or custom builds:

```bash
# Prerequisites
sudo apt-get update
sudo apt-get install -y python3 python3-dev python3-venv \
    network-manager dnsmasq avahi-daemon iptables openssh-client \
    build-essential debhelper dh-python fakeroot

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
cd /opt
git clone https://github.com/pamir-ai/distiller-services.git
cd distiller-services

# Install dependencies
uv sync

# Build Debian package (optional)
./build-deb.sh

# Or run directly in development mode (requires root)
sudo uv run python distiller_wifi.py --no-hardware --debug
```

### Post-Installation Verification

```bash
# Check service status
sudo systemctl status distiller-wifi.service

# View recent logs
sudo journalctl -u distiller-wifi -n 50

# Verify network interfaces
nmcli device status

# Check mDNS advertisement
avahi-browse -a -t | grep -i distiller

# Test web interface (in AP mode)
curl http://192.168.4.1:8080

# Test web interface (in client mode, replace xxxx with device ID)
curl http://distiller-xxxx.local:8080
```

## Configuration

### Environment Variables

All configuration options can be set via environment variables with the `DISTILLER_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISTILLER_AP_SSID_PREFIX` | `Distiller` | Access Point SSID prefix |
| `DISTILLER_AP_IP` | `192.168.4.1` | Access Point IP address |
| `DISTILLER_AP_CHANNEL` | `6` | WiFi channel (1-11 for 2.4GHz) |
| `DISTILLER_WEB_HOST` | `0.0.0.0` | Web server bind address |
| `DISTILLER_WEB_PORT` | `8080` | Web server port |
| `DISTILLER_ENABLE_CAPTIVE_PORTAL` | `True` | Enable captive portal detection |
| `DISTILLER_DISPLAY_ENABLED` | `True` | Enable e-ink display updates |
| `DISTILLER_DISPLAY_UPDATE_INTERVAL` | `2.0` | Display update interval (seconds) |
| `DISTILLER_TUNNEL_ENABLED` | `True` | Enable tunnel service |
| `DISTILLER_TUNNEL_PROVIDER` | `frp` | Primary tunnel provider (frp or pinggy) |
| `DISTILLER_DEVICES_DOMAIN` | `devices.pamir.ai` | FRP domain for device URLs |
| `DISTILLER_FRP_SERVICE_NAME` | `frpc.service` | FRP systemd service name |
| `DISTILLER_DEVICE_SERIAL` | `None` | Device serial override |
| `DISTILLER_DEVICE_ENV_PATH` | `/etc/pamir/device.env` | Path to device env file |
| `DISTILLER_TUNNEL_REFRESH_INTERVAL` | `3300` | Pinggy refresh interval (seconds) |
| `DISTILLER_TUNNEL_SSH_PORT` | `443` | SSH port for tunnel connection |
| `DISTILLER_PINGGY_ACCESS_TOKEN` | `None` | Pinggy access token (optional) |
| `DISTILLER_TUNNEL_MAX_RETRIES` | `3` | Maximum tunnel retry attempts |
| `DISTILLER_TUNNEL_RETRY_DELAY` | `30` | Delay between retries (seconds) |
| `DISTILLER_DEBUG` | `False` | Enable debug logging |

### Configuration via .env File

Create `/opt/distiller-services/.env`:

```bash
DISTILLER_DEBUG=True
DISTILLER_WEB_PORT=9090
DISTILLER_TUNNEL_PROVIDER=pinggy
DISTILLER_PINGGY_ACCESS_TOKEN=your_token_here
```

### Device Identity Configuration

Device identity is managed automatically via MAC address but can be inspected:

```bash
# View device configuration
cat /var/lib/distiller/device_config.json

# Example output:
{
  "device_id": "a3f2",
  "hostname": "distiller-a3f2",
  "ap_ssid": "Distiller-A3F2",
  "created_at": "2024-01-15T10:30:00.000000"
}
```

## Usage

### Starting and Stopping

```bash
# Start service
sudo systemctl start distiller-wifi.service

# Stop service
sudo systemctl stop distiller-wifi.service

# Restart service
sudo systemctl restart distiller-wifi.service

# Enable auto-start on boot
sudo systemctl enable distiller-wifi.service

# Disable auto-start
sudo systemctl disable distiller-wifi.service

# View service status
sudo systemctl status distiller-wifi.service
```

### Accessing the Web Interface

**In Access Point Mode:**
1. Connect to WiFi network: `Distiller-XXXX` (where XXXX is device ID)
2. Use password displayed on device screen or in logs
3. Browser should automatically open to setup page (captive portal)
4. If not, navigate to: `http://192.168.4.1:8080`

**In Client Mode:**
1. Connect to same WiFi network as device
2. Navigate to: `http://distiller-xxxx.local:8080` (where xxxx is device ID)
3. Or use IP address shown on device display

**Via Tunnel (Remote Access):**
1. Check tunnel URL on device display or in logs
2. Navigate to FRP URL: `https://SERIAL.devices.pamir.ai`
3. Or Pinggy URL: `https://random.free.pinggy.link`

### Monitoring Service

```bash
# View live logs
sudo journalctl -u distiller-wifi -f

# View last 100 lines
sudo journalctl -u distiller-wifi -n 100

# View logs since boot
sudo journalctl -u distiller-wifi -b

# View logs with timestamp
sudo journalctl -u distiller-wifi -o short-iso

# Filter by priority (errors only)
sudo journalctl -u distiller-wifi -p err

# Check log file (if file logging enabled)
sudo tail -f /var/log/distiller/distiller-wifi.log
```

### WebSocket Connection

For real-time state updates, connect to the WebSocket endpoint:

```javascript
// JavaScript example
const ws = new WebSocket('ws://distiller-xxxx.local:8080/ws');

ws.onmessage = (event) => {
    const state = JSON.parse(event.data);
    console.log('Connection state:', state.state);
    console.log('Current SSID:', state.ssid);
    console.log('IP address:', state.ip_address);
    console.log('Tunnel URL:', state.tunnel_url);
};
```

State updates are broadcast whenever the connection state changes.

## API Reference

### REST Endpoints

#### GET /api/networks

Scan and return available WiFi networks.

**Response:**
```json
{
  "networks": [
    {
      "ssid": "MyNetwork",
      "signal": 85,
      "security": "WPA2",
      "in_use": false
    }
  ]
}
```

#### POST /api/connect

Initiate WiFi connection.

**Request:**
```json
{
  "ssid": "MyNetwork",
  "password": "password123"
}
```

**Response (202 Accepted):**
```json
{
  "status": "connecting",
  "session_id": "uuid-here"
}
```

#### GET /api/status

Get current connection state.

**Response:**
```json
{
  "state": "CONNECTED",
  "ssid": "MyNetwork",
  "ip_address": "192.168.1.100",
  "tunnel_url": "https://abc123.devices.pamir.ai",
  "error": null,
  "session_id": "uuid-here"
}
```

#### POST /api/disconnect

Disconnect from current network and return to AP mode.

**Response:**
```json
{
  "status": "disconnecting"
}
```

### WebSocket Protocol

**Endpoint:** `ws://<host>:<port>/ws`

**Message Format:**
```json
{
  "state": "CONNECTED",
  "ssid": "MyNetwork",
  "ip_address": "192.168.1.100",
  "tunnel_url": "https://abc123.devices.pamir.ai",
  "error": null,
  "session_id": "uuid-here"
}
```

Messages are sent automatically on state changes. No subscription or heartbeat required.

### Connection States

| State | Description |
|-------|-------------|
| `AP_MODE` | Device running as access point, waiting for configuration |
| `SWITCHING` | Transitioning between network modes |
| `CONNECTING` | Attempting to connect to specified WiFi network |
| `CONNECTED` | Successfully connected to WiFi network |
| `FAILED` | Connection attempt failed, returning to AP mode |
| `DISCONNECTED` | Manually disconnected from network |

## Development

### Development Environment Setup

```bash
# Clone repository
git clone https://github.com/pamir-ai/distiller-services.git
cd distiller-services

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
make setup

# Or manually:
uv sync
```

### Development Commands

```bash
# Run in development mode (requires root for NetworkManager access)
make run

# Run with custom arguments
make run ARGS="--port 9090"

# Run without hardware dependencies
sudo uv run python distiller_wifi.py --no-hardware --debug

# Code quality checks
make lint         # Run all linters (ruff, mypy, shellcheck)
make fix          # Auto-fix formatting issues

# Individual linting
uv run ruff check .                    # Lint only
uv run ruff format .                   # Format only
uv run mypy --ignore-missing-imports . # Type check

# Build Debian package
make build

# Clean build artifacts
./build-deb.sh clean
```

### Code Style

The project follows strict code quality guidelines:

- **Line Length**: 100 characters (ruff and black)
- **Type Hints**: Full Pydantic typing throughout
- **Async/Await**: All I/O operations use async patterns
- **Import Sorting**: isort with black profile
- **Linting**: ruff with pycodestyle, pyflakes, flake8-bugbear
- **Type Checking**: mypy with Python 3.11 target

### Project Structure

```
distiller-services/
├── core/                       # Core business logic
│   ├── state.py               # State machine & persistence
│   ├── network_manager.py     # NetworkManager wrapper
│   ├── config.py              # Settings & environment
│   ├── device_config.py       # Device identity management
│   ├── captive_portal.py      # Captive portal iptables
│   └── avahi_service.py       # mDNS advertisement
├── services/                  # Service implementations
│   ├── web_server.py          # FastAPI application
│   ├── display_service.py     # E-ink display updates
│   ├── display_screens.py     # Screen layouts
│   ├── display_layouts.py     # Layout components
│   ├── display_theme.py       # Design tokens
│   └── tunnel_service.py      # FRP/Pinggy tunnels
├── templates/                 # Jinja2 HTML templates
├── static/                    # CSS, JavaScript assets
├── debian/                    # Debian packaging files
├── scripts/                   # Utility scripts
├── distiller_wifi.py          # Main entry point
├── pyproject.toml             # Python project config
├── Makefile                   # Development commands
└── build-deb.sh               # Universal Debian builder
```

### Building Debian Packages

```bash
# Build for ARM64 (default)
./build-deb.sh

# Build for current architecture
./build-deb.sh native

# Build for specific architecture
TARGET_ARCH=amd64 ./build-deb.sh

# Check dependencies before building
./build-deb.sh check

# Clean and rebuild
./build-deb.sh clean
./build-deb.sh
```

Package output: `dist/distiller-services_3.0.0_arm64.deb`

## Network Configuration Details

### Captive Portal Mechanism

The captive portal uses a two-part system:

1. **Wildcard DNS**: NetworkManager's dnsmasq is configured to return the gateway IP for all DNS queries via `/etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf`

2. **OS Detection Endpoints**: HTTP redirects for connectivity checks:
   - Android: `/generate_204`, `/gen_204`
   - iOS: `/hotspot-detect.html`, `/library/test/success.html`, `/success.txt`
   - Windows: `/ncsi.txt`, `/connecttest.txt`
   - Firefox: `/canonical.html`
   - Kindle: `/kindle-wifi/wifistub.html`

All endpoints return HTTP 302 redirects to the setup page.

### mDNS Resolution

Avahi service advertises the HTTP service with TXT records:

```xml
<service>
  <type>_http._tcp</type>
  <port>8080</port>
  <txt-record>path=/</txt-record>
  <txt-record>version=2.0</txt-record>
  <txt-record>device=distiller</txt-record>
</service>
```

Service file location: `/etc/avahi/services/distiller-wifi.service`

### Tunnel URL Patterns

**FRP (Fast Reverse Proxy):**
- URL format: `https://{SERIAL}.{DEVICES_DOMAIN}`
- Example: `https://ABC123456.devices.pamir.ai`
- Requires device serial in `/etc/pamir/device.env`
- Systemd service: `frpc.service`

**Pinggy:**
- Free tier: `https://random-id.subdomain.free.pinggy.link`
- Persistent: `https://custom-subdomain.pinggy.link`
- Refresh interval: 55 minutes (free) or 24 hours (persistent)
- Requires SSH client

## File Locations

### Installation Directories

| Path | Purpose |
|------|---------|
| `/opt/distiller-services/` | Service installation directory |
| `/opt/distiller-services/.venv/` | Python virtual environment |
| `/opt/distiller-sdk/` | Distiller SDK installation |

### State and Configuration

| Path | Purpose |
|------|---------|
| `/var/lib/distiller/state.json` | Persistent state (network, tunnel) |
| `/var/lib/distiller/device_config.json` | Device identity configuration |
| `/etc/pamir/device.env` | Device serial number (if available) |
| `/etc/NetworkManager/system-connections/` | NetworkManager connection profiles |
| `/etc/NetworkManager/dnsmasq-shared.d/` | Captive portal DNS configuration |
| `/etc/avahi/services/` | Avahi mDNS service files |

### Logs

| Path | Purpose |
|------|---------|
| `/var/log/distiller/distiller-wifi.log` | Service log file (rotating, 10MB) |
| `journalctl -u distiller-wifi` | Systemd journal logs |

### Systemd Service

| Path | Purpose |
|------|---------|
| `/lib/systemd/system/distiller-wifi.service` | Systemd unit file |

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status distiller-wifi.service

# View recent errors
sudo journalctl -u distiller-wifi -n 50 -p err

# Check if NetworkManager is running
sudo systemctl status NetworkManager

# Verify Python environment
/opt/distiller-services/.venv/bin/python --version

# Check permissions
ls -la /opt/distiller-services/distiller_wifi.py
```

### Cannot Access Web Interface

```bash
# Verify service is running
sudo systemctl is-active distiller-wifi.service

# Check listening ports
sudo ss -tlnp | grep 8080

# Verify AP mode is active
nmcli connection show --active | grep Distiller

# Check firewall rules
sudo iptables -L -n -v

# Test local connectivity
curl http://localhost:8080

# Verify mDNS hostname
avahi-resolve --name distiller-xxxx.local
```

### Captive Portal Not Working

```bash
# Check dnsmasq configuration
cat /etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf

# Verify DNS is working
nslookup google.com 192.168.4.1

# Check iptables NAT rules
sudo iptables -t nat -L -n -v

# Restart NetworkManager
sudo systemctl restart NetworkManager
sudo systemctl restart distiller-wifi.service
```

### WiFi Connection Fails

```bash
# Check WiFi device status
nmcli device status

# Scan for networks
nmcli device wifi list

# Check NetworkManager logs
sudo journalctl -u NetworkManager -n 100

# Verify credentials in state file
cat /var/lib/distiller/state.json

# Test connection manually
sudo nmcli device wifi connect "SSID" password "password"
```

### E-ink Display Not Updating

```bash
# Check if display is enabled
grep -i display /var/lib/distiller/state.json

# Verify display hardware
ls -la /dev/spidev*

# Check SDK installation
ls -la /opt/distiller-sdk/

# View display debug images (if hardware unavailable)
ls -la /tmp/distiller_display.png

# Check display service logs
sudo journalctl -u distiller-wifi | grep -i display
```

### Tunnel Not Working

```bash
# Check tunnel service status
sudo journalctl -u distiller-wifi | grep -i tunnel

# Verify FRP service (if using FRP)
sudo systemctl status frpc.service

# Check device serial
cat /etc/pamir/device.env

# Verify SSH connectivity (if using Pinggy)
ssh -T a.pinggy.io

# Check network connectivity
ping -c 4 8.8.8.8
```

### State File Corruption

```bash
# Check for backup
ls -la /var/lib/distiller/state.json.backup

# Restore from backup
sudo cp /var/lib/distiller/state.json.backup /var/lib/distiller/state.json

# Or reset state (will start fresh)
sudo rm /var/lib/distiller/state.json
sudo systemctl restart distiller-wifi.service
```

### High CPU Usage

```bash
# Check process status
top -p $(pgrep -f distiller_wifi)

# View detailed resource usage
sudo systemd-cgtop

# Check for network event storms
sudo journalctl -u distiller-wifi -f | grep -i event

# Disable display updates if needed
echo "DISTILLER_DISPLAY_ENABLED=False" | sudo tee -a /opt/distiller-services/.env
sudo systemctl restart distiller-wifi.service
```

## Known Issues

See [TODO.md](TODO.md) for detailed technical implementation plan addressing:

- Network connectivity validation (currently checks cached state only)
- Event monitoring implementation (stubbed in network_manager.py:626-642)
- Connection request serialization
- AP password stability during connection retries
- Display update race conditions during rapid state changes

## Contributing

Contributions are welcome. Please follow these guidelines:

1. Fork the repository and create a feature branch
2. Follow the code style guidelines (ruff, mypy)
3. Add tests for new functionality
4. Update documentation as needed
5. Submit a pull request with clear description

### Code Quality Requirements

- All code must pass `make lint` without errors
- Type hints required for all functions
- Async/await for all I/O operations
- No emojis or casual language in code comments
- Line length limit: 100 characters

## License

Copyright (c) 2024 PamirAI Incorporated

Licensed under the MIT License. See LICENSE file for details.

## Support

For issues and support:

- GitHub Issues: https://github.com/pamir-ai/distiller-services/issues
- Email: support@pamir.ai
- Documentation: https://docs.pamir.ai/distiller-services

## Related Projects

- [distiller-sdk](https://github.com/pamir-ai/distiller-sdk) - Core hardware SDK
- [distiller-telemetry](https://github.com/pamir-ai/distiller-telemetry) - Device registration service
- [distiller-update](https://github.com/pamir-ai/distiller-update) - APT update checker
- [distiller-test-harness](https://github.com/pamir-ai/distiller-test-harness) - Test suite

## Acknowledgments

Built with FastAPI, NetworkManager, Avahi, and the Python ecosystem.
