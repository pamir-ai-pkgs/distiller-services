# Distiller WiFi Provisioning Service

Modern asynchronous WiFi provisioning system for Distiller edge computing devices, providing secure network configuration through access point mode, client connectivity, and remote access via encrypted tunnels.

## Overview

Distiller WiFi Provisioning Service is a production-ready network configuration system designed for ARM-based embedded devices. The service orchestrates multiple subsystems to provide seamless WiFi setup through a web-based interface, automatic service discovery via mDNS, visual feedback through e-ink displays, and secure remote access through dual tunnel mechanisms.

**Target Platforms:** Raspberry Pi CM5, Radxa Zero 3, Radxa Zero 3W
**Architecture:** ARM64 Linux

### Key Capabilities

The service operates in two primary modes: Access Point (AP) mode for initial configuration and Client mode for normal operation. During AP mode, the device creates a temporary WiFi network with captive portal support, allowing users to configure WiFi credentials through any web browser. Once configured, the device transitions to Client mode, connecting to the specified network while maintaining remote access through FRP or Pinggy tunnels.

## Features

### Network Management

- **Access Point Mode**: Creates temporary WiFi hotspot with dynamically generated secure passwords
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

- **E-ink Display Support**: Event-driven updates for EPD128x250 (native: 128×250, mounted: 250×128) and EPD240x416 (240×416) displays
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

Recommended for production deployments:

```bash
sudo dpkg -i distiller-sdk_3.0.0_arm64.deb
sudo dpkg -i distiller-services_3.0.0_arm64.deb
sudo systemctl enable distiller-wifi.service
sudo systemctl start distiller-wifi.service
```

### From Source Installation

For development or custom builds:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-dev python3-venv \
    network-manager dnsmasq avahi-daemon iptables openssh-client \
    build-essential debhelper dh-python fakeroot

curl -LsSf https://astral.sh/uv/install.sh | sh

cd /opt
git clone https://github.com/pamir-ai/distiller-services.git
cd distiller-services

uv sync

just build

sudo uv run python distiller_wifi.py --no-hardware --debug
```

### Verification

```bash
sudo systemctl status distiller-wifi.service
sudo journalctl -u distiller-wifi -n 50
nmcli device status
avahi-browse -a -t | grep -i distiller
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

### Configuration File

Create `/opt/distiller-services/.env`:

```bash
DISTILLER_DEBUG=True
DISTILLER_WEB_PORT=9090
DISTILLER_TUNNEL_PROVIDER=pinggy
DISTILLER_PINGGY_ACCESS_TOKEN=your_token_here
```

## Usage

### Starting and Stopping

```bash
sudo systemctl start distiller-wifi.service
sudo systemctl stop distiller-wifi.service
sudo systemctl restart distiller-wifi.service
sudo systemctl enable distiller-wifi.service
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
sudo journalctl -u distiller-wifi -f
sudo journalctl -u distiller-wifi -n 100
sudo journalctl -u distiller-wifi -b
sudo journalctl -u distiller-wifi -o short-iso
sudo journalctl -u distiller-wifi -p err
```

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

### Setup

```bash
git clone https://github.com/pamir-ai/distiller-services.git
cd distiller-services
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### Development Commands

```bash
just run
just run ARGS="--port 9090"
sudo uv run python distiller_wifi.py --no-hardware --debug
```

### Code Quality

```bash
just lint
just fix
uv run ruff check .
uv run ruff format .
uv run mypy --ignore-missing-imports .
```

### Building

```bash
just build
just build native
TARGET_ARCH=amd64 just build
just clean
```

Package output: `dist/distiller-services_3.0.0_arm64.deb`

### Code Style

- **Line Length**: 100 characters
- **Type Hints**: Full Pydantic typing throughout
- **Async/Await**: All I/O operations use async patterns
- **Import Sorting**: isort with black profile
- **Linting**: ruff with pycodestyle, pyflakes, flake8-bugbear
- **Type Checking**: mypy with Python 3.11 target

### Project Structure

```
distiller-services/
├── core/
│   ├── state.py
│   ├── network_manager.py
│   ├── config.py
│   ├── device_config.py
│   ├── captive_portal.py
│   └── avahi_service.py
├── services/
│   ├── web_server.py
│   ├── display_service.py
│   ├── display_screens.py
│   ├── display_layouts.py
│   ├── display_theme.py
│   └── tunnel_service.py
├── templates/
├── static/
├── debian/
├── scripts/
├── distiller_wifi.py
├── pyproject.toml
└── Justfile
```

## File Locations

| Path | Purpose |
|------|---------|
| `/opt/distiller-services/` | Service installation directory |
| `/opt/distiller-services/.venv/` | Python virtual environment |
| `/var/lib/distiller/state.json` | Persistent state (network, tunnel) |
| `/var/lib/distiller/device_config.json` | Device identity configuration |
| `/etc/pamir/device.env` | Device serial number (if available) |
| `/etc/NetworkManager/system-connections/` | NetworkManager connection profiles |
| `/etc/NetworkManager/dnsmasq-shared.d/` | Captive portal DNS configuration |
| `/etc/avahi/services/` | Avahi mDNS service files |
| `/var/log/distiller/distiller-wifi.log` | Service log file (rotating, 10MB) |
| `/lib/systemd/system/distiller-wifi.service` | Systemd unit file |

## Troubleshooting

### Service Won't Start

```bash
sudo systemctl status distiller-wifi.service
sudo journalctl -u distiller-wifi -n 50 -p err
sudo systemctl status NetworkManager
/opt/distiller-services/.venv/bin/python --version
```

### Cannot Access Web Interface

```bash
sudo systemctl is-active distiller-wifi.service
sudo ss -tlnp | grep 8080
nmcli connection show --active | grep Distiller
curl http://localhost:8080
avahi-resolve --name distiller-xxxx.local
```

### Captive Portal Not Working

```bash
cat /etc/NetworkManager/dnsmasq-shared.d/80-distiller-captive.conf
nslookup google.com 192.168.4.1
sudo iptables -t nat -L -n -v
sudo systemctl restart NetworkManager
sudo systemctl restart distiller-wifi.service
```

### WiFi Connection Fails

```bash
nmcli device status
nmcli device wifi list
sudo journalctl -u NetworkManager -n 100
cat /var/lib/distiller/state.json
sudo nmcli device wifi connect "SSID" password "password"
```

### E-ink Display Not Updating

```bash
grep -i display /var/lib/distiller/state.json
ls -la /dev/spidev*
ls -la /opt/distiller-sdk/
ls -la /tmp/distiller_display.png
sudo journalctl -u distiller-wifi | grep -i display
```

### Tunnel Not Working

```bash
sudo journalctl -u distiller-wifi | grep -i tunnel
sudo systemctl status frpc.service
cat /etc/pamir/device.env
ssh -T a.pinggy.io
ping -c 4 8.8.8.8
```

## Contributing

Contributions are welcome. Please follow these guidelines:

1. Fork the repository and create a feature branch
2. Follow the code style guidelines (ruff, mypy)
3. Add tests for new functionality
4. Update documentation as needed
5. Submit a pull request with clear description

### Code Quality Requirements

- All code must pass `just lint` without errors
- Type hints required for all functions
- Async/await for all I/O operations
- No emojis or casual language in code comments
- Line length limit: 100 characters

## License

Copyright (c) 2025 PamirAI Incorporated

Licensed under the MIT License. See LICENSE file for details.

## Support

For issues and support:

- GitHub Issues: https://github.com/pamir-ai-pkgs/distiller-services/issues
- Email: founders@pamir.ai

## Related Projects

- [distiller-sdk](https://github.com/pamir-ai/distiller-sdk) - Core hardware SDK
- [distiller-update](https://github.com/pamir-ai/distiller-update) - APT update checker

## Acknowledgments

Built with FastAPI, NetworkManager, Avahi, and the Python ecosystem.
