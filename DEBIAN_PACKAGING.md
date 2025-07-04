# Debian Packaging for Distiller CM5 Services

This document describes the Debian packaging setup for the Distiller CM5 Services project.

## Overview

The project now includes modern Debian packaging that:
- Uses `/opt/distiller-cm5-services` as the installation directory (instead of `/home/distiller`)
- Handles dependencies intelligently through apt and pip
- Provides systemd service integration
- Creates proper symlinks for easy command access
- Includes lintian checks for package quality

## Package Structure

### Installation Locations

- **Main application**: `/opt/distiller-cm5-services/`
- **Systemd services**: `/lib/systemd/system/`
- **Documentation**: `/usr/share/doc/distiller-cm5-services/`
- **Command symlinks**: `/usr/local/bin/`

### Command Access

After installation, the following commands are available:

- `distiller-wifi-setup` - WiFi setup service
- `distiller-tunnel` - Pinggy tunnel service  
- `distiller-mdns` - mDNS service

## Dependencies

### System Dependencies (via apt)

**Required:**
- `python3-fastapi` (>= 0.104.1)
- `python3-uvicorn` (>= 0.24.0)
- `python3-pydantic` (>= 2.5.0)
- `python3-jinja2` (>= 3.1.2)
- `python3-multipart` (>= 0.0.6)
- `python3-pil` (>= 8.0.0)
- `python3-numpy` (>= 1.20.0)
- `python3-qrcode` (>= 8.2)
- `python3-zeroconf` (>= 0.147.0)
- `python3-aiohttp` (>= 3.8.0)
- `systemd`
- `network-manager`
- `python3-dbus`

**Recommended** (for full functionality):
- `python3-evdev` (>= 1.9.2) - Button input support
- `python3-spidev` (>= 3.7) - SPI interface for e-ink display
- `python3-lgpio` (>= 0.2.2.0) - GPIO access for e-ink display
- `fonts-liberation` - Fallback fonts

**Suggested:**
- `avahi-daemon` - For mDNS functionality

### Intelligent Dependency Handling

The packaging system handles dependencies intelligently:

1. **System packages first**: Most dependencies are installed via apt as system packages
2. **Pip fallback**: Missing dependencies are installed via pip in postinst script
3. **Graceful degradation**: Optional dependencies (like e-ink display support) don't prevent installation
4. **Version requirements**: Ensures compatible versions are installed

## Building Packages

### Prerequisites

Install build dependencies:
```bash
sudo apt update
sudo apt install debhelper dh-python dpkg-dev lintian devscripts
```

Or use the build script to install them automatically:
```bash
./build-deb.sh deps
```

### Build Commands

The `build-deb.sh` script provides several build options:

```bash
# Build full package (source + binary)
./build-deb.sh

# Build with specific version
./build-deb.sh -v 1.0.1-1

# Build only binary package
./build-deb.sh binary

# Build only source package
./build-deb.sh source

# Clean build artifacts
./build-deb.sh clean

# Run lintian checks
./build-deb.sh check
```

### Build Process

1. **Dependency check**: Installs required build tools
2. **Validation**: Checks package structure and required files
3. **Version update**: Updates changelog if version specified
4. **Build**: Creates source and/or binary packages
5. **Quality check**: Runs lintian for package validation
6. **Organization**: Moves artifacts to `dist/` directory

## Installation

### From Built Package

```bash
# Install the package
sudo dpkg -i dist/distiller-cm5-services_*.deb

# Fix any dependency issues
sudo apt-get install -f
```

### Post-Installation

The package automatically:
- Creates symlinks in `/usr/local/bin/`
- Sets proper permissions
- Enables systemd services
- Installs missing Python dependencies via pip

Start services manually:
```bash
sudo systemctl start distiller-wifi
sudo systemctl start pinggy-tunnel
```

## Service Management

### WiFi Setup Service

```bash
# Status
sudo systemctl status distiller-wifi

# Start/Stop
sudo systemctl start distiller-wifi
sudo systemctl stop distiller-wifi

# Logs
sudo journalctl -u distiller-wifi -f
```

### Pinggy Tunnel Service

```bash
# Status
sudo systemctl status pinggy-tunnel

# Start/Stop
sudo systemctl start pinggy-tunnel
sudo systemctl stop pinggy-tunnel

# Logs
sudo journalctl -u pinggy-tunnel -f
```

## Package Removal

### Remove Package

```bash
# Remove package but keep configuration
sudo apt remove distiller-cm5-services

# Remove package and configuration
sudo apt purge distiller-cm5-services
```

### What Gets Removed

- Main application files in `/opt/distiller-cm5-services/`
- Systemd service files
- Command symlinks
- Generated images and logs
- Empty directories (fonts directory preserved if populated)

## Development

### Package Structure

```
debian/
├── changelog          # Version history
├── compat            # Debhelper compatibility level
├── control           # Package metadata and dependencies
├── copyright         # License information
├── postinst          # Post-installation script
├── postrm            # Post-removal script
├── prerm             # Pre-removal script
├── rules             # Build rules
└── source/
    └── format        # Source package format
```

### Key Features

1. **Modern debhelper**: Uses debhelper-compat (= 13)
2. **Python integration**: Uses dh-python for Python packaging
3. **Systemd integration**: Automatic service management
4. **Intelligent dependencies**: Separates system vs pip packages
5. **Quality assurance**: Lintian checks for package quality
6. **Flexible installation**: Graceful handling of optional dependencies

### Adding Dependencies

Edit `debian/control`:
- Add to `Depends:` for required packages
- Add to `Recommends:` for optional but useful packages  
- Add to `Suggests:` for packages that enhance functionality

### Updating Version

```bash
# Update version and rebuild
./build-deb.sh -v 1.0.1-1 full
```

## Troubleshooting

### Build Issues

1. **Missing dependencies**: Run `./build-deb.sh deps`
2. **Permission errors**: Ensure `debian/rules` is executable
3. **Lintian warnings**: Check `build-deb.sh check` output

### Installation Issues

1. **Dependency conflicts**: Run `sudo apt-get install -f`
2. **Service start failures**: Check system logs with `journalctl`
3. **Permission issues**: Ensure running as root for network operations

### Package Quality

Use lintian to check package quality:
```bash
./build-deb.sh check
```

Common issues and fixes:
- **debian-watch-file-is-missing**: Add `debian/watch` file for upstream monitoring
- **no-homepage-field**: Already included in `debian/control`
- **binary-without-manpage**: Consider adding man pages for commands

## Migration from Previous Setup

If upgrading from the previous `/home/distiller` setup:

1. Stop existing services
2. Install new package
3. Update any custom configurations
4. Start new services

The new package handles the path migration automatically. 