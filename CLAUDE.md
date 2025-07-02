# Distiller CM5 Services - Claude Development Guide

## Project Overview
WiFi setup and network management service for Raspberry Pi CM5-based Distiller devices. Provides automated WiFi configuration with web interface, e-ink display integration, and mDNS discovery.

## Key Commands

### Running the Service
```bash
# Development mode with verbose logging
sudo python3 wifi_setup_service.py --verbose --no-startup-check

# Production mode
sudo python3 wifi_setup_service.py
```

### Testing & Validation
```bash
# Check service status
sudo systemctl status wifi-setup

# View logs
sudo journalctl -u wifi-setup -f

# Test NetworkManager connection
nmcli dev wifi
```

### Code Quality
```bash
# Run linting (if configured)
# TODO: Add linting command when available

# Run tests (if configured)  
# TODO: Add test command when available
```

## Architecture

### Core Components
- `wifi_setup_service.py` - Main orchestrator service
- `network/wifi_manager.py` - NetworkManager interface for WiFi operations  
- `network/wifi_server.py` - FastAPI web server for setup interface
- `mdns_service.py` - Network discovery and permanent device access
- `wifi_info_display.py` - E-ink display visual feedback

### API Endpoints
- Setup Server (Port 8080):
  - `GET /` - Main setup interface
  - `POST /api/connect` - Initiate WiFi connection
  - `GET /api/status` - Current connection status

- mDNS Service (Port 8000):
  - `GET /` - Device dashboard
  - `GET /wifi_status` - Network information

## Development Guidelines

### Code Style
- Follow existing Python conventions in the codebase
- Use type hints where appropriate
- Maintain consistent error handling patterns
- Log important operations and errors

### Hardware Integration
- E-ink display support is optional (check `EINK_AVAILABLE`)
- Button input uses evdev library (check `EVDEV_AVAILABLE`)
- Service requires root privileges for network operations

### Dependencies
- FastAPI/Uvicorn for web services
- Zeroconf for mDNS functionality  
- Pillow/NumPy for e-ink display
- NetworkManager Python bindings
- evdev for button input (optional)
- spidev/lgpio for hardware control (optional)

## Common Tasks

### Adding New API Endpoints
1. Add route to `network/wifi_server.py`
2. Update corresponding HTML template if needed
3. Add any required static assets to `static/`

### Modifying WiFi Logic
1. Update `network/wifi_manager.py` for NetworkManager operations
2. Test with different network configurations
3. Ensure proper error handling and recovery

### Updating Display Content
1. Modify image generation in `wifi_info_display.py`
2. Test on actual e-ink hardware or with `--no-eink` flag
3. Consider display refresh timing

### SSH Tunnel Service (Pinggy)
1. **Service**: `pinggy_tunnel_service.py` - Creates SSH tunnel through free.pinggy.io
2. **Installation**: `sudo bash install-tunnel-service.sh`
3. **Features**:
   - Automatic tunnel establishment after WiFi connection
   - Hourly refresh (55 minutes) before expiration
   - QR code display on e-ink screen integrated with WiFi info
   - Port 3000 exposed through tunnel
4. **Commands**:
   ```bash
   sudo systemctl status pinggy-tunnel  # Check status
   sudo journalctl -u pinggy-tunnel -f  # View logs
   sudo systemctl restart pinggy-tunnel # Restart service
   ```

## Debugging Tips

### Network Issues
- Check NetworkManager status: `sudo systemctl status NetworkManager`
- Verify hotspot creation: `nmcli connection show`
- Monitor network interfaces: `ip addr`

### Web Interface Problems
- Check port availability: `sudo lsof -i :8080`
- Verify FastAPI routes are registered
- Check browser console for JavaScript errors

### Hardware Integration
- Test with `--no-button-check` flag to bypass button detection
- Use `--no-eink` flag to disable display functionality
- Check SPI/GPIO permissions for hardware access