# Distiller CM5 WiFi Service

Modern, unified WiFi provisioning service for Raspberry Pi CM5 devices with E-ink display support.
Features a single-service architecture with async Python, real-time WebSocket updates, and
persistent mDNS discovery.

## Architecture Overview

This project has been completely refactored from a multi-service architecture to a **single unified
service** using modern Python async/await patterns. The new architecture provides:

- **Single Service**: One process managing all functionality (replacing 4 separate services)
- **Async Architecture**: Built on FastAPI with full async/await support
- **Real-time Updates**: WebSocket connections for live status updates
- **Persistent mDNS**: Device remains discoverable during network transitions
- **Monochrome UI**: Pure black and white terminal-style interface
- **State-driven**: Event-based state management with callbacks

## Features

### Core Functionality

- **Always-On AP Mode**: Starts in Access Point mode for easy setup
- **mDNS Discovery**: Access via `http://distiller-xxxx.local:8080`
- **Seamless Transitions**: Maintains user connection during network switches
- **WebSocket Updates**: Real-time status without polling
- **Session Management**: Preserves user sessions across network changes

### WiFi Management

- **Automatic Setup**: Creates hotspot when no connection available
- **Unique Device IDs**: Random 4-character suffix prevents conflicts
- **Network Scanning**: Real-time discovery with signal strength
- **Smart Reconnection**: Automatic recovery from connection failures
- **Change Network**: Switch networks without losing configuration session

### E-ink Display Support

- **QR Codes**: Easy mobile device connection during setup
- **Status Display**: Current network info and connection state
- **Progress Indicators**: Visual feedback during operations
- **Monochrome Design**: Optimized for 1-bit displays
- **Auto-refresh**: Periodic updates based on state changes

### Remote Access

- **Pinggy Tunnels**: SSH tunnel integration for remote access
- **Persistent Tunnels**: Support for Pinggy access tokens (no expiry)
- **Free Tunnels**: Automatic 55-minute refresh for free tier
- **Auto-refresh**: Maintains tunnel connectivity
- **State-aware**: Only active when WiFi connected

## Quick Start

### Prerequisites

- Linux system with NetworkManager
- Python 3.11+
- **Root privileges required** (for NetworkManager operations and system directories)
- E-ink display hardware (optional)

### Installation with uv (Recommended)

Using [uv](https://github.com/astral-sh/uv) for fast, reliable Python package management:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/Pamir-AI/distiller-cm5-services
cd distiller-cm5-services

# Install dependencies with uv
uv sync

# Run in development mode (requires root)
sudo uv run python distiller_wifi.py --no-hardware --debug
```

### Installation with pip (Fallback)

If uv is not available:

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run in development mode (requires root)
sudo python distiller_wifi.py --no-hardware --debug
```

### Debian Package Installation

For production deployment:

```bash
# Build package
./build-deb.sh

# Install
sudo dpkg -i dist/distiller-cm5-services_*.deb
sudo apt-get install -f  # Fix any dependencies

# Start service
sudo systemctl start distiller-wifi
sudo systemctl status distiller-wifi
```

## Configuration

The service can be configured through environment variables or configuration files.

### Pinggy Persistent Tunnels

To use persistent tunnels that don't expire, obtain a Pinggy access token from
[pinggy.io](https://pinggy.io) and configure it:

#### Method 1: Environment Variable

```bash
# Copy example file
cp .env.example .env

# Edit .env and add your token
DISTILLER_PINGGY_ACCESS_TOKEN=your_token_here
```

#### Method 2: Configuration File

```bash
# Edit tunnel_config.json and add your token
{
  "pinggy_access_token": "your_token_here"
}
```

With a token configured:

- Tunnels persist without expiry
- Refresh interval extends to 24 hours
- URLs remain stable for reliable remote access

Without a token:

- Free tunnels expire after 60 minutes
- Service auto-refreshes every 55 minutes
- URLs change on each refresh

## Usage

### Basic Operation

1. **Device starts** → Creates WiFi hotspot `Distiller-XXXX`
2. **Connect** → Join hotspot with password `setupwifi123`
3. **Configure** → Open browser to `http://distiller-xxxx.local:8080`
4. **Select Network** → Choose your WiFi and enter password
5. **Connected** → Device joins network, remains accessible via mDNS

### Command Line Options

```bash
sudo python distiller_wifi.py [OPTIONS]
```

| Option          | Default          | Description               |
| --------------- | ---------------- | ------------------------- |
| `--host`        | `0.0.0.0`        | Web server host binding   |
| `--port`        | `8080`           | Web server port           |
| `--ap-ssid`     | `Distiller-{ID}` | Access Point SSID         |
| `--ap-password` | `setupwifi123`   | Access Point password     |
| `--no-hardware` | `False`          | Disable hardware features |
| `--debug`       | `False`          | Enable debug logging      |
| `--config`      | `config.json`    | Configuration file path   |

### Development Mode

Run without hardware for development:

```bash
# Using uv (preferred)
sudo uv run python distiller_wifi.py --no-hardware --debug

# Using pip virtual environment
sudo .venv/bin/python distiller_wifi.py --no-hardware --debug

# Access the web interface
open http://localhost:8080
```

## Project Structure

```text
distiller-cm5-services/
├── distiller_wifi.py           # Main application entry point
├── core/                       # Core modules
│   ├── config.py              # Pydantic configuration
│   ├── state.py               # State management with events
│   ├── network_manager.py     # NetworkManager wrapper
│   └── mdns_service.py        # mDNS/Zeroconf service
├── services/                   # Service modules
│   ├── web_server.py          # FastAPI application
│   ├── display_service.py     # E-ink display manager
│   └── tunnel_service.py      # Pinggy SSH tunnels
├── templates/                  # Jinja2 HTML templates
│   ├── base.html              # Base template with monochrome design
│   ├── setup.html             # WiFi setup interface
│   ├── connecting.html        # Connection progress
│   └── status.html            # Connection status
├── static/                     # Static web assets
│   ├── css/
│   │   └── monochrome.css    # Pure black/white styling
│   └── js/
│       └── app.js             # WebSocket client
├── debian/                     # Debian packaging
├── pyproject.toml             # uv project configuration
├── requirements.txt           # pip requirements (fallback)
└── README.md                  # This file
```

## API Reference

### REST Endpoints

| Endpoint          | Method | Description                 |
| ----------------- | ------ | --------------------------- |
| `/`               | GET    | Main web interface          |
| `/api/status`     | GET    | Current connection status   |
| `/api/networks`   | GET    | Available WiFi networks     |
| `/api/connect`    | POST   | Connect to network          |
| `/api/disconnect` | POST   | Disconnect and return to AP |
| `/api/config`     | GET    | Current configuration       |

### WebSocket

Connect to `/ws` for real-time updates:

```javascript
const ws = new WebSocket('ws://distiller-xxxx.local:8080/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Status update:', data);
};
```

### Status Response

```json
{
  "state": "CONNECTED",
  "ssid": "HomeNetwork",
  "ip_address": "192.168.1.100",
  "signal_strength": -45,
  "uptime": 3600,
  "tunnel_url": "https://abc123.pinggy.io"
}
```

## State Management

The service uses a state machine with the following states:

```text
INITIALIZING → SETUP_MODE → CONNECTING → CONNECTED
                   ↑            ↓            ↓
                   └────────────←────────────┘
```

### States

- **INITIALIZING**: Service startup and initialization
- **SETUP_MODE**: Access Point active, awaiting configuration
- **CONNECTING**: Attempting to connect to selected network
- **CONNECTED**: Successfully connected to WiFi network
- **FAILED**: Connection attempt failed (returns to SETUP_MODE)

## Display Interface

### Monochrome UI Design

The web interface uses a strict 1-bit color scheme:

- **Colors**: Pure black (#000000) and white (#FFFFFF) only
- **Typography**: Monospace fonts for terminal aesthetic
- **Graphics**: ASCII art and box-drawing characters
- **No gradients**: No shadows, gradients, or intermediate colors
- **High contrast**: Maximum readability on all devices

### E-ink Display

The service automatically updates the E-ink display based on state:

- **Setup Mode**: QR code with hotspot credentials
- **Connecting**: Progress indicator
- **Connected**: Network details and tunnel URL
- **Failed**: Error message with retry instructions

## Device Identity Management

The service maintains a persistent device identity with the following features:

- **Unique Device ID**: 4-character alphanumeric identifier (e.g., "ab12")
- **Persistent Configuration**: Survives reboots and service restarts
- **Automatic Hostname**: Sets system hostname to `distiller-xxxx`
- **mDNS Registration**: Accessible via `distiller-xxxx.local`
- **AP SSID Generation**: Creates unique hotspot name `Distiller-XXXX`

Device configuration is stored in `/var/lib/distiller/device_config.json` and includes:

- Device ID
- Hostname
- AP SSID
- Creation timestamp

## Security Features

### Dynamic AP Password Generation

For enhanced security, the service generates a new Access Point password on each startup:

- **12-character random password** using cryptographically secure generation
- **Displayed in service logs** during initialization
- **Shown on E-ink display** if hardware is connected
- **Never stored persistently** - regenerated on each restart
- **Uses Python's `secrets` module** for secure randomness

To view the current AP password:

```bash
sudo journalctl -u distiller-wifi | grep "AP PASSWORD"
```

## Development

### Development Scripts

The project includes comprehensive development tools:

#### dev.sh - Development Helper Script

```bash
./dev.sh setup              # Install dependencies (prefers uv)
./dev.sh run                # Start with --no-hardware --debug
./dev.sh run --port 9090    # Custom port
./dev.sh test               # Run tests
./dev.sh lint               # Run linters
./dev.sh format             # Format code
./dev.sh clean              # Clean temporary files
./dev.sh reset              # Reset environment
./dev.sh shell              # Start development shell
./dev.sh status             # Check environment
```

#### lint.sh - Comprehensive Linting

```bash
./lint.sh --check           # Check for issues (default)
./lint.sh --fix             # Auto-fix formatting
./lint.sh --verbose         # Detailed output
```

Supports:

- Python: ruff, black, isort, mypy
- HTML: djlint, prettier
- JavaScript: eslint, prettier
- CSS: stylelint, prettier
- JSON/YAML: prettier, yamllint
- Markdown: markdownlint
- Shell: shellcheck

#### generate_eink_previews.py - Display Preview Generator

```bash
python generate_eink_previews.py
```

Generates preview images of all E-ink display states:

- Setup mode with QR code
- Connecting animation
- Connected status
- Tunnel active with remote access QR
- Initialization screen

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/Pamir-AI/distiller-cm5-services
cd distiller-cm5-services

# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with hot-reload (requires sudo)
sudo uv run python distiller_wifi.py --no-hardware --debug --reload
```

### Code Style

- **Type hints**: Full typing with Pydantic models
- **Async/await**: All I/O operations are async
- **No emojis**: Clean, professional code without emoji decorations
- **Error handling**: Comprehensive exception handling with recovery
- **Logging**: Structured logging with appropriate levels

### Testing

```bash
# Run unit tests
uv run pytest tests/

# Run with coverage
uv run pytest --cov=core --cov=services tests/

# Test hardware integration (requires hardware)
sudo uv run python distiller_wifi.py --debug

# Test WebSocket connection
wscat -c ws://localhost:8080/ws
```

## Deployment

### Systemd Service

The service is managed by systemd:

```bash
# Start service
sudo systemctl start distiller-wifi

# Enable on boot
sudo systemctl enable distiller-wifi

# View logs
sudo journalctl -u distiller-wifi -f

# Restart service
sudo systemctl restart distiller-wifi
```

### Configuration

Create `/etc/distiller/config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8080,
  "ap_ssid_prefix": "Distiller",
  "ap_password": "setupwifi123",
  "mdns_type": "_distiller._tcp.local.",
  "state_file": "/var/lib/distiller/state.json",
  "enable_tunnel": true,
  "enable_display": true
}
```

### Environment Variables

```bash
# Override configuration with environment variables
export DISTILLER_PORT=9090
export DISTILLER_AP_PASSWORD=mysecurepassword
export DISTILLER_DEBUG=true
```

## Troubleshooting

### Common Issues

**Service won't start:**

```bash
# Check for port conflicts
sudo netstat -tlnp | grep 8080

# Verify NetworkManager
systemctl status NetworkManager

# Check permissions
ls -la /var/lib/distiller/
```

**Can't connect to hotspot:**

```bash
# List WiFi networks
nmcli device wifi list

# Check hotspot status
nmcli connection show

# Verify IP address
ip addr show
```

**WebSocket connection fails:**

```bash
# Test WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: test" -H "Sec-WebSocket-Version: 13" \
  http://localhost:8080/ws
```

**E-ink display not working:**

```bash
# Test display module
uv run python -c "from services.display_service import DisplayService; print('Display module OK')"

# Run without display (requires sudo)
sudo uv run python distiller_wifi.py --no-hardware
```

### Debug Mode

Enable comprehensive logging:

```bash
# Set debug environment variable
export DISTILLER_DEBUG=true

# Or use command line flag (requires sudo)
sudo uv run python distiller_wifi.py --debug

# View detailed logs
sudo journalctl -u distiller-wifi -f --output=json-pretty
```

## Building from Source

### Prerequisites

```bash
# Install build dependencies
sudo apt install python3-dev build-essential
sudo apt install debhelper dh-python dpkg-dev

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Build Process

```bash
# Build Debian package
./build-deb.sh

# Build specific version
./build-deb.sh -v 2.0.0-1

# Clean build artifacts
./build-deb.sh clean
```

### Creating Release

```bash
# Tag version
git tag -a v2.0.0 -m "Release version 2.0.0"

# Push tags
git push origin v2.0.0

# Build release package
./build-deb.sh -v 2.0.0-1
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`uv run pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- Use type hints for all functions
- Write async code for I/O operations
- Follow PEP 8 style guide
- Add unit tests for new features
- Update documentation as needed
- No emoji in source code

## License

Copyright (c) 2025 Pamir AI. All rights reserved.

## Support

For issues and questions:

- Create an issue on GitHub
- Check the troubleshooting section
- Enable debug mode for detailed diagnostics
- Test with `--no-hardware` flag for hardware-independent issues

---

**Important**: This service **requires root privileges** to run. The application will check for root
access at startup and exit with an error message if not running as root. This is necessary for:

- NetworkManager operations (creating/managing WiFi connections)
- Writing to system directories (`/var/lib/distiller`, `/var/log/distiller`)
- Binding to network interfaces for mDNS service

Always use `sudo` when running the application:

```bash
sudo uv run python distiller_wifi.py --no-hardware --debug
# or
sudo ./dev.sh run
```
