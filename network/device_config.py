"""
Device Configuration Manager

Manages persistent device identity including random naming, mDNS configuration,
and system hostname management to prevent conflicts between multiple devices.
"""

import os
import json
import random
import string
import socket
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from zeroconf import ServiceInfo, Zeroconf, IPVersion
from zeroconf.asyncio import AsyncZeroconf
import threading
import time
import asyncio

logger = logging.getLogger(__name__)


class DeviceConfigManager:
    """Manages device configuration and identity"""

    def __init__(
        self, config_dir: str = "/etc/distiller", service_name: str = "distiller-wifi"
    ):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "device-config.json"
        self.service_name = service_name
        self.zeroconf: Optional[AsyncZeroconf] = None
        self.registered_services = []
        self._config_cache: Optional[Dict[str, Any]] = None
        self._zeroconf_thread: Optional[threading.Thread] = None
        self._running = False
        self._use_sudo = self._should_use_sudo()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Initialize configuration
        self._load_or_create_config()

    def _should_use_sudo(self) -> bool:
        """Determine if we should use sudo for privileged commands"""
        # Use sudo if we're running as the 'distiller' user
        current_user = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'
        return current_user == 'distiller'

    def _build_command(self, base_cmd: list[str]) -> list[str]:
        """Build command with sudo prefix if needed for privileged operations"""
        privileged_commands = {'hostname', 'systemctl', 'ip', 'nmcli'}
        
        if self._use_sudo and base_cmd and base_cmd[0] in privileged_commands:
            return ['sudo'] + base_cmd
        return base_cmd

    def _generate_random_suffix(self, length: int = 4) -> str:
        """Generate random alphanumeric suffix"""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    def _is_distiller_hostname(self, hostname: str) -> bool:
        """Check if hostname is in distiller-XXXX format"""
        import re
        # Check for distiller- followed by exactly 4 alphanumeric characters
        pattern = r'^distiller-[a-zA-Z0-9]{4}$'
        return bool(re.match(pattern, hostname))

    def _get_current_hostname(self) -> str:
        """Get current system hostname"""
        try:
            result = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get current hostname: {e}")
        
        # Fallback to socket method
        try:
            import socket
            return socket.gethostname()
        except Exception as e:
            logger.error(f"Failed to get hostname via socket: {e}")
            return "unknown"

    def _load_or_create_config(self) -> Dict[str, Any]:
        """Load existing config or create new one with random identifiers"""
        try:
            current_hostname = self._get_current_hostname()
            
            if self.config_file.exists():
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    # Validate required fields
                    required_fields = ["device_id", "hotspot_suffix", "hostname"]
                    if all(field in config for field in required_fields):
                        self._config_cache = config
                        logger.info(f"Loaded device config: {config['device_id']}")
                        
                        # Check if system hostname is already in distiller-XXXX format
                        if self._is_distiller_hostname(current_hostname) and current_hostname != config["hostname"]:
                            logger.info(f"System already has valid distiller hostname '{current_hostname}', preserving it")
                            # Update config to match system hostname
                            config["hostname"] = current_hostname
                            config["device_id"] = current_hostname
                            # Extract suffix from hostname for other fields
                            suffix = current_hostname.replace("distiller-", "").upper()
                            config["hotspot_suffix"] = suffix
                            config["hotspot_ssid"] = f"DistillerSetup-{suffix}"
                            config["friendly_name"] = f"Distiller {suffix}"
                            
                            # Save updated config
                            with open(self.config_file, "w") as f:
                                json.dump(config, f, indent=2)
                            os.chmod(self.config_file, 0o644)
                            
                            logger.info(f"Updated config to match system hostname: {current_hostname}")
                        elif current_hostname != config["hostname"]:
                            logger.info(f"Hostname mismatch: system='{current_hostname}', config='{config['hostname']}' - updating system")
                            self._update_system_hostname(config["hostname"])
                        
                        return config
                    else:
                        logger.warning("Invalid config file, regenerating...")

            # Check if system already has a valid distiller hostname
            if self._is_distiller_hostname(current_hostname):
                logger.info(f"System already has valid distiller hostname '{current_hostname}', using it for new config")
                # Extract suffix from existing hostname
                suffix = current_hostname.replace("distiller-", "").upper()
                config = {
                    "device_id": current_hostname,
                    "hotspot_suffix": suffix,
                    "hostname": current_hostname,
                    "friendly_name": f"Distiller {suffix}",
                    "hotspot_ssid": f"DistillerSetup-{suffix}",
                    "hotspot_password": "setup123",
                    "web_port": 8080,
                    "created_at": int(time.time()),
                    "version": "1.0",
                }
            else:
                # Generate new configuration with random suffix
                random_suffix = self._generate_random_suffix()
                config = {
                    "device_id": f"distiller-{random_suffix.lower()}",
                    "hotspot_suffix": random_suffix,
                    "hostname": f"distiller-{random_suffix.lower()}",
                    "friendly_name": f"Distiller {random_suffix}",
                    "hotspot_ssid": f"DistillerSetup-{random_suffix}",
                    "hotspot_password": "setup123",
                    "web_port": 8080,
                    "created_at": int(time.time()),
                    "version": "1.0",
                }

            # Save configuration
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)

            # Set appropriate permissions
            os.chmod(self.config_file, 0o644)

            self._config_cache = config
            logger.info(f"Created new device config: {config['device_id']}")

            # Only update system hostname if it's not already in distiller-XXXX format
            if not self._is_distiller_hostname(current_hostname):
                self._update_system_hostname(config["hostname"])

            return config

        except Exception as e:
            logger.error(f"Error managing device config: {e}")
            # Fallback configuration
            return {
                "device_id": "distiller-temp",
                "hotspot_suffix": "TEMP",
                "hostname": "distiller-temp",
                "friendly_name": "Distiller Device",
                "hotspot_ssid": "DistillerSetup-TEMP",
                "hotspot_password": "setup123",
                "web_port": 8080,
            }

    def get_config(self) -> Dict[str, Any]:
        """Get current device configuration"""
        if self._config_cache is None:
            self._config_cache = self._load_or_create_config()
        return self._config_cache.copy()

    def get_device_id(self) -> str:
        """Get unique device identifier"""
        return self.get_config()["device_id"]

    def get_hostname(self) -> str:
        """Get device hostname"""
        return self.get_config()["hostname"]

    def get_friendly_name(self) -> str:
        """Get human-readable device name"""
        return self.get_config()["friendly_name"]

    def get_hotspot_ssid(self) -> str:
        """Get hotspot SSID with random suffix"""
        return self.get_config()["hotspot_ssid"]

    def get_hotspot_password(self) -> str:
        """Get hotspot password"""
        return self.get_config()["hotspot_password"]

    def get_web_port(self) -> int:
        """Get web server port"""
        return self.get_config().get("web_port", 8080)

    def _update_system_hostname(self, hostname: str) -> bool:
        """Update system hostname with graceful fallback"""
        try:
            current_hostname = self._get_current_hostname()
            logger.info(f"Attempting to update system hostname from '{current_hostname}' to '{hostname}'")
            
            success = False
            
            # Method 1: Try hostnamectl (preferred for systemd)
            try:
                cmd = self._build_command(["hostnamectl", "set-hostname", hostname])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info(f"Successfully updated hostname using hostnamectl")
                    success = True
                else:
                    logger.warning(f"hostnamectl failed (exit {result.returncode}): {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"hostnamectl method failed: {e}")

            # Method 2: Try writing to /etc/hostname directly
            if not success:
                try:
                    hostname_cmd = self._build_command(["tee", "/etc/hostname"])
                    result = subprocess.run(hostname_cmd, input=f"{hostname}\n", 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        logger.info("Updated /etc/hostname successfully")
                        # Set runtime hostname
                        subprocess.run(self._build_command(["hostname", hostname]), 
                                     check=False, timeout=5)
                        success = True
                    else:
                        logger.warning(f"Failed to write /etc/hostname: {result.stderr.strip()}")
                except Exception as e:
                    logger.warning(f"Direct /etc/hostname update failed: {e}")

            # If we can't update system hostname, just continue with service
            if not success:
                logger.warning(f"Could not update system hostname due to permissions")
                logger.warning(f"Service will continue with hostname mismatch:")
                logger.warning(f"  System hostname: {current_hostname}")
                logger.warning(f"  Service config:  {hostname}")
                logger.warning(f"  mDNS will advertise: {current_hostname}.local")
                logger.warning(f"  Service will claim: {hostname}.local")
                return False
            
            # Update /etc/hosts (optional, continue if fails)
            try:
                self._update_hosts_file(hostname)
            except Exception as e:
                logger.warning(f"Failed to update /etc/hosts: {e}")

            # Update Avahi configuration (optional, continue if fails)
            try:
                self._update_avahi_config(hostname)
                
                # Restart avahi-daemon to pick up new hostname
                subprocess.run(self._build_command(["systemctl", "restart", "avahi-daemon"]), 
                             check=False, timeout=10)
                logger.info("Restarted avahi-daemon")
            except Exception as e:
                logger.warning(f"Failed to update avahi config: {e}")

            # Verify the change
            new_hostname = self._get_current_hostname()
            if new_hostname == hostname:
                logger.info(f"Hostname successfully updated to: {hostname}")
                return True
            else:
                logger.warning(f"Hostname verification: expected '{hostname}', got '{new_hostname}'")
                return False

        except Exception as e:
            logger.error(f"Failed to update hostname: {e}")
            return False

    def _update_hosts_file(self, hostname: str):
        """Update /etc/hosts with new hostname"""
        try:
            hosts_content = []
            updated = False

            # Read current hosts file
            with open("/etc/hosts", "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("127.0.1.1"):
                        # Update localhost alias line
                        hosts_content.append(f"127.0.1.1\t{hostname}")
                        updated = True
                    else:
                        hosts_content.append(line)

            # Add localhost alias if not found
            if not updated:
                hosts_content.append(f"127.0.1.1\t{hostname}")

            # Write updated hosts file
            with open("/etc/hosts", "w") as f:
                f.write("\n".join(hosts_content) + "\n")

        except Exception as e:
            logger.error(f"Failed to update /etc/hosts: {e}")

    def _update_avahi_config(self, hostname: str):
        """Update Avahi daemon configuration with hostname"""
        try:
            avahi_config_path = Path("/etc/avahi/avahi-daemon.conf")

            if not avahi_config_path.exists():
                # Create basic Avahi configuration
                config_content = f"""[server]
host-name={hostname}
domain-name=local
browse-domains=local
use-ipv4=yes
use-ipv6=yes
allow-interfaces=wlan0,eth0
deny-interfaces=lo
check-response-ttl=no
use-iff-running=no

[wide-area]
enable-wide-area=yes

[publish]
disable-publishing=no
disable-user-service-publishing=no
add-service-cookie=no
publish-addresses=yes
publish-hinfo=yes
publish-workstation=yes
publish-domain=yes
publish-dns-servers=no,192.168.4.1
publish-resolv-conf-dns-servers=yes
publish-aaaa-on-ipv4=yes
publish-a-on-ipv6=no

[reflector]
enable-reflector=no
reflect-ipv=no

[rlimits]
rlimit-core=0
rlimit-data=4194304
rlimit-fsize=0
rlimit-nofile=768
rlimit-stack=4194304
rlimit-nproc=3
"""
            else:
                # Update existing configuration
                with open(avahi_config_path, "r") as f:
                    content = f.read()

                # Replace hostname line or add it
                lines = content.split("\n")
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("host-name="):
                        lines[i] = f"host-name={hostname}"
                        updated = True
                        break

                if not updated:
                    # Find [server] section and add hostname
                    for i, line in enumerate(lines):
                        if line == "[server]":
                            lines.insert(i + 1, f"host-name={hostname}")
                            break

                config_content = "\n".join(lines)

            # Write configuration
            with open(avahi_config_path, "w") as f:
                f.write(config_content)

            os.chmod(avahi_config_path, 0o644)

            # Restart Avahi daemon
            subprocess.run(self._build_command(["systemctl", "restart", "avahi-daemon"]), check=False)

            logger.info(f"Updated Avahi configuration with hostname: {hostname}")

        except Exception as e:
            logger.error(f"Failed to update Avahi configuration: {e}")

    def start_mdns_service(self, ip_address: str, port: Optional[int] = None) -> bool:
        """Start mDNS service advertisement"""
        try:
            # Always stop existing service first to prevent conflicts
            if self.zeroconf is not None:
                self.stop_mdns_service()
                # Give some time for cleanup
                time.sleep(1)

            port = port or self.get_web_port()
            device_id = self.get_device_id()
            friendly_name = self.get_friendly_name()

            # Validate IP address format
            try:
                socket.inet_aton(ip_address)
            except socket.error:
                logger.error(f"Invalid IP address for mDNS: {ip_address}")
                return False

            # Use AsyncZeroconf in a background thread to avoid EventLoopBlocked
            def run_async_mdns():
                """Run AsyncZeroconf in background thread"""
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    async def start_service():
                        self.zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

                        # Service type for HTTP web interface
                        service_type = "_http._tcp.local."
                        service_name = f"{device_id}.{service_type}"

                        # Service properties
                        properties = {
                            "device_id": device_id.encode("utf-8"),
                            "friendly_name": friendly_name.encode("utf-8"),
                            "service": "distiller-wifi".encode("utf-8"),
                            "version": "1.0".encode("utf-8"),
                            "setup": "true".encode("utf-8"),
                        }

                        # Create service info
                        service_info = ServiceInfo(
                            service_type,
                            service_name,
                            addresses=[socket.inet_aton(ip_address)],
                            port=port,
                            properties=properties,
                            server=f"{device_id}.local.",
                        )

                        await self.zeroconf.async_register_service(service_info)
                        self.registered_services.append(service_info)

                        logger.info(
                            f"Started mDNS service: {service_name} on {ip_address}:{port}"
                        )
                        return True

                    return loop.run_until_complete(start_service())

                except Exception as e:
                    logger.error(f"Error in async mDNS thread: {e}")
                    return False
                finally:
                    if loop and not loop.is_closed():
                        loop.close()

            # Run in background thread to avoid blocking
            if self._zeroconf_thread and self._zeroconf_thread.is_alive():
                self._zeroconf_thread.join(timeout=2)

            self._zeroconf_thread = threading.Thread(target=run_async_mdns, daemon=True)
            self._zeroconf_thread.start()
            self._zeroconf_thread.join(timeout=10)  # Wait up to 10 seconds for startup

            return len(self.registered_services) > 0

        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}", exc_info=True)
            # Clean up on failure
            if self.zeroconf is not None:
                try:
                    asyncio.run(self.zeroconf.async_close())
                except:
                    pass
                self.zeroconf = None
            self.registered_services.clear()
            return False

    def stop_mdns_service(self):
        """Stop mDNS service advertisement"""
        try:
            if self.zeroconf is not None:
                # Use async methods in a background thread
                def run_async_stop():
                    """Run async stop in background thread"""
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        async def stop_service():
                            # Unregister services with timeout to prevent hanging
                            for service_info in self.registered_services:
                                try:
                                    if self.zeroconf is not None:
                                        await self.zeroconf.async_unregister_service(
                                            service_info
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to unregister service {service_info.name}: {e}"
                                    )

                            # Close zeroconf with timeout
                            try:
                                if self.zeroconf is not None:
                                    await self.zeroconf.async_close()
                            except Exception as e:
                                logger.warning(f"Error closing zeroconf: {e}")

                        loop.run_until_complete(stop_service())

                    except Exception as e:
                        logger.warning(f"Error in async stop thread: {e}")
                    finally:
                        if loop and not loop.is_closed():
                            loop.close()

                # Run stop in background thread
                stop_thread = threading.Thread(target=run_async_stop, daemon=True)
                stop_thread.start()
                stop_thread.join(timeout=5)  # Wait up to 5 seconds for cleanup

                self.zeroconf = None
                self.registered_services.clear()

                logger.info("Stopped mDNS service")

        except Exception as e:
            logger.error(f"Error stopping mDNS service: {e}")
            # Force cleanup even if there are errors
            self.zeroconf = None
            self.registered_services.clear()

    def transition_mdns_to_network(self, ip_address: str) -> bool:
        """Transition mDNS service to new network"""
        try:
            # Validate IP address format
            if not self._validate_ip_address(ip_address):
                logger.error(f"Invalid IP address for mDNS transition: {ip_address}")
                return False

            # Stop current service if running (with extended timeout for network transitions)
            self.stop_mdns_service()

            # Add delay to ensure clean transition and allow network interfaces to settle
            import time

            time.sleep(5)  # Increased delay for network transition

            # Start service on new network
            return self.start_mdns_service(ip_address)
        except Exception as e:
            logger.error(f"Error transitioning mDNS to new network: {e}")
            return False

    def _validate_ip_address(self, ip_address: str) -> bool:
        """Validate IP address format"""
        try:
            import ipaddress

            ipaddress.ip_address(ip_address)
            return True
        except ValueError:
            return False

    def discover_mdns_devices(self, timeout: float = 5.0) -> list[Dict[str, Any]]:
        """Discover other Distiller devices on the network via mDNS"""
        discovered_devices = []

        try:
            from zeroconf import ServiceBrowser

            class DistillerServiceListener:
                def __init__(self):
                    self.devices = []

                def add_service(self, zeroconf, service_type, name):
                    try:
                        info = zeroconf.get_service_info(service_type, name)
                        if info:
                            properties = {}
                            if info.properties:
                                for key, value in info.properties.items():
                                    properties[key.decode("utf-8")] = value.decode(
                                        "utf-8"
                                    )

                            # Check if this is a Distiller device
                            if properties.get("service") == "distiller-wifi":
                                device = {
                                    "name": name,
                                    "addresses": [
                                        socket.inet_ntoa(addr)
                                        for addr in info.addresses
                                    ],
                                    "port": info.port,
                                    "properties": properties,
                                    "hostname": info.server.rstrip("."),
                                }
                                self.devices.append(device)
                                logger.info(
                                    f"Discovered Distiller device: {properties.get('device_id', 'unknown')}"
                                )

                    except Exception as e:
                        logger.error(f"Error processing discovered service: {e}")

                def remove_service(self, zeroconf, service_type, name):
                    pass

                def update_service(self, zeroconf, service_type, name):
                    pass

            # Create listener and browser
            listener = DistillerServiceListener()
            zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            browser = ServiceBrowser(zeroconf, "_http._tcp.local.", listener)

            # Wait for discovery
            time.sleep(timeout)

            # Cleanup
            browser.cancel()
            zeroconf.close()

            discovered_devices = listener.devices

        except Exception as e:
            logger.error(f"Error during mDNS discovery: {e}")

        return discovered_devices

    def get_device_mdns_id(self, device_id: Optional[str] = None) -> Optional[str]:
        """Get mDNS URL for this device or another device by ID"""
        if device_id is None:
            device_id = self.get_device_id()

        return f"http://{device_id}.local"

    def get_device_mdns_url(self, device_id: Optional[str] = None) -> Optional[str]:
        """Get mDNS URL for this device or another device by ID"""
        if device_id is None:
            device_id = self.get_device_id()

        return f"http://{device_id}.local:{self.get_web_port()}"

    def __del__(self):
        """Cleanup on destruction"""
        self.stop_mdns_service()


# Global instance
_device_config = None


def get_device_config() -> DeviceConfigManager:
    """Get global device configuration instance"""
    global _device_config
    if _device_config is None:
        _device_config = DeviceConfigManager()
    return _device_config
