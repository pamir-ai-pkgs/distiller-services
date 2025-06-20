# Distiller CM5 Services

WiFi setup and network management service for Raspberry Pi CM5-based Distiller devices. This service provides an automated WiFi configuration system with web interface, e-ink display integration, and mDNS discovery capabilities.

## Overview

The Distiller CM5 Services creates a seamless WiFi setup experience for embedded devices by:

- Creating a temporary WiFi hotspot for initial configuration
- Providing a web-based interface for network selection and authentication
- Supporting e-ink display integration for visual feedback
- Automatically transitioning to mDNS service discovery after successful connection
- Offering both temporary setup and permanent device access endpoints

## Architecture

### Core Components

- **WiFi Setup Service** (`wifi_setup_service.py`) - Main orchestrator service
- **WiFi Manager** (`network/wifi_manager.py`) - NetworkManager interface for WiFi operations
- **WiFi Server** (`network/wifi_server.py`) - FastAPI web server for setup interface
- **mDNS Service** (`mdns_service.py`) - Network discovery and permanent device access
- **E-ink Display** (`wifi_info_display.py`, `eink_display_flush.py`) - Visual status display

### Web Interface

- **Setup Interface** - WiFi network selection and password entry
- **Status Pages** - Real-time connection progress and results
- **Device Dashboard** - Post-connection device information and access

## Features

### WiFi Management
- Automatic hotspot creation for initial setup
- Support for WPA/WPA2 secured and open networks
- Network connection validation and retry logic
- Graceful fallback to setup mode on connection failures

### User Interface
- Responsive web interface with professional Pamir AI branding
- Real-time connection status updates
- Mobile-friendly design with touch-optimized controls
- Static text progress indicators for reliable user feedback

### Hardware Integration
- E-ink display support for headless operation
- Button input detection for manual setup triggering
- GPIO integration for hardware status indicators
- Automatic hardware capability detection

### Network Discovery
- mDNS/Bonjour service advertisement
- Automatic hostname resolution (.local domains)
- Persistent device accessibility after setup
- Network interface monitoring and reporting

## Installation

### Prerequisites

- Raspberry Pi CM5 or compatible device
- Python 3.8 or higher
- NetworkManager for WiFi management
- Root privileges for network operations

### Dependencies

Install required Python packages:

```bash
pip install -r requirements.txt
```

Key dependencies include:
- FastAPI and Uvicorn for web services
- Zeroconf for mDNS functionality
- Pillow and NumPy for e-ink display rendering
- NetworkManager integration libraries

### System Service Installation

1. Clone the repository to the target device:
```bash
git clone https://github.com/Pamir-AI/distiller-cm5-services distiller-cm5-services
cd distiller-cm5-services
```

2. Install as a systemd service:
```bash
sudo bash install-service.sh
```

3. Start the service:
```bash
sudo systemctl start wifi-setup
```

## Configuration

### Environment Variables

Configure the service through environment variables or systemd service file:

- `WIFI_HOTSPOT_SSID` - Setup hotspot network name (default: "SetupWiFi")
- `WIFI_HOTSPOT_PASSWORD` - Setup hotspot password (default: "setupwifi123")
- `WIFI_SETUP_NO_EINK` - Disable e-ink display functionality (default: false)

### Service Parameters

The main service accepts several command-line arguments:

```bash
python3 wifi_setup_service.py --help
```

Key options:
- `--ssid` - Custom hotspot SSID
- `--password` - Custom hotspot password
- `--device-name` - Input device name for button detection
- `--no-button-check` - Disable button checking
- `--no-eink` - Disable e-ink display
- `--mdns-hostname` - Custom mDNS hostname
- `--mdns-port` - mDNS service port (default: 8000)

## Usage

### Initial Setup

1. Power on the device
2. Connect to the "SetupWiFi" network (password: "setupwifi123")
3. Navigate to http://192.168.4.1:8080 in a web browser
4. Select your WiFi network and enter credentials
5. Click "Connect" and wait for confirmation

### Post-Setup Access

After successful WiFi connection, the device becomes accessible via:

- **mDNS**: `http://[hostname].local:8000`
- **Direct IP**: `http://[device-ip]:8000`

### Service Management

Control the service using systemctl commands:

```bash
# Check status
sudo systemctl status wifi-setup

# View logs
sudo journalctl -u wifi-setup -f

# Restart service
sudo systemctl restart wifi-setup

# Stop service
sudo systemctl stop wifi-setup
```

## API Endpoints

### Setup Server (Port 8080)

- `GET /` - Main setup interface
- `GET /api/status` - Current connection status
- `POST /api/connect` - Initiate WiFi connection
- `GET /wifi_status` - Connection status page

### mDNS Service (Port 8000)

- `GET /` - Device dashboard
- `GET /wifi_status` - Network information page

## Hardware Integration

### E-ink Display

The service supports e-ink displays for headless operation:

- Automatic display of setup instructions
- Real-time connection status updates
- Network information display after successful connection
- QR code generation for easy mobile access

### Button Input

Physical button integration for manual setup triggering:

- Configurable input device detection
- Hold-to-activate setup mode
- Automatic hardware capability detection

## Development

### Project Structure

```
distiller-cm5-services/
├── wifi_setup_service.py      # Main service orchestrator
├── mdns_service.py            # mDNS service implementation
├── network/                   # Network management modules
│   ├── wifi_manager.py        # WiFi operations
│   ├── wifi_server.py         # Web server
│   └── network_utils.py       # Network utilities
├── templates/                 # HTML templates
│   ├── index.html             # Setup interface
│   ├── wifi_status.html       # Status page
│   ├── mdns_home.html         # Device dashboard
│   └── mdns_wifi_status.html  # mDNS status page
├── static/                    # Static web assets
│   ├── css/style.css          # Stylesheet
│   ├── js/wifi-setup.js       # Frontend JavaScript
│   └── images/                # Images and logos
├── wifi_info_display.py       # E-ink display functions
├── eink_display_flush.py      # E-ink driver
└── requirements.txt           # Python dependencies
```

### Testing

Run the service in development mode:

```bash
python3 wifi_setup_service.py --verbose --no-startup-check
```

This bypasses the initial connection check and enables debug logging.

## Troubleshooting

### Common Issues

**Service fails to start:**
- Check NetworkManager is running: `sudo systemctl status NetworkManager`
- Verify permissions: Service must run as root for network operations
- Check logs: `sudo journalctl -u wifi-setup -n 50`

**Web interface not accessible:**
- Confirm hotspot is active: `nmcli dev wifi`
- Check firewall settings
- Verify port 8080 is not blocked

**mDNS resolution fails:**
- Install Avahi daemon: `sudo apt install avahi-daemon`
- Enable mDNS: `sudo systemctl enable --now avahi-daemon`
- Check network configuration

**E-ink display not working:**
- Verify hardware connections
- Check SPI interface is enabled
- Install required GPIO libraries

### Logs and Debugging

The service provides comprehensive logging:

```bash
# Real-time logs
sudo journalctl -u wifi-setup -f

# Recent logs with details
sudo journalctl -u wifi-setup -n 100 --no-pager

# Enable debug logging
sudo systemctl edit wifi-setup
# Add: Environment=WIFI_SETUP_VERBOSE=true
```

## License

This project is part of the Pamir AI Distiller ecosystem. Please refer to the project license for usage terms and conditions.

## Support

For technical support and documentation, please refer to the Pamir AI Distiller documentation or contact the development team. 
