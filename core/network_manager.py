"""NetworkManager wrapper for WiFi operations."""

import asyncio
import logging
import os
import re
import shutil
import stat
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class WiFiNetwork:
    def __init__(self, ssid: str, signal: int, security: str, in_use: bool = False):
        self.ssid = ssid
        self.signal = signal
        self.security = security
        self.in_use = in_use

    def __repr__(self):
        return f"WiFiNetwork(ssid={self.ssid}, signal={self.signal}, security={self.security})"


class NetworkManager:
    def __init__(self):
        self.wifi_device: str | None = None
        self._device_cache_time = 0.0
        self._device_cache_timeout = 300
        self._is_ap_mode = False
        self._last_scan_results: list[WiFiNetwork] = []
        self.ap_connection_name = "Distiller-AP"
        self._dnsmasq_config_dir = Path("/etc/NetworkManager/dnsmasq-shared.d")
        self._dnsmasq_config_file = self._dnsmasq_config_dir / "80-distiller-captive.conf"

    async def initialize(self) -> None:
        await self._detect_wifi_device()
        if self.wifi_device:
            logger.info(f"WiFi device detected: {self.wifi_device}")
        else:
            logger.warning("No WiFi device detected")

    async def _ensure_dns_port_available(self) -> None:
        """Stop conflicting DNS services so NetworkManager's dnsmasq can start."""

        if shutil.which("systemctl") is None:
            return

        for service in ("dnsmasq",):
            returncode, _, _ = await self._run_command(
                ["systemctl", "is-active", "--quiet", service]
            )

            if returncode == 0:
                logger.warning(
                    f"Stopping conflicting DNS service '{service}' to free port 53"
                )
                await self._run_command(["systemctl", "stop", service])

            returncode, _, _ = await self._run_command(
                ["systemctl", "is-enabled", "--quiet", service]
            )

            if returncode == 0:
                logger.info(f"Disabling conflicting DNS service '{service}'")
                await self._run_command(["systemctl", "disable", service])

    async def _configure_captive_dns(self, gateway_ip: str) -> bool:
        """Configure NetworkManager's dnsmasq for wildcard DNS (captive portal).

        Creates a dnsmasq config file that makes all DNS queries return the gateway IP.
        This triggers captive portal detection on Android, iOS, Windows, etc.
        """
        try:
            # Ensure config directory exists
            self._dnsmasq_config_dir.mkdir(parents=True, exist_ok=True)

            # Create dnsmasq config for wildcard DNS
            config_content = f"""# Distiller WiFi Captive Portal DNS Configuration
# This file is automatically managed - do not edit manually

# Return gateway IP for all DNS queries (wildcard DNS)
address=/#/{gateway_ip}

# Prevent DNS loops
no-resolv
no-poll
"""

            # NetworkManager already binds dnsmasq to the shared interface, so we
            # rely on its defaults. Explicit bind directives here can conflict
            # with NM-managed parameters and break AP activation.

            # Write config file
            self._dnsmasq_config_file.write_text(config_content)
            logger.info(f"Created dnsmasq captive portal config: {self._dnsmasq_config_file}")

            # NetworkManager will reload dnsmasq when starting the AP connection
            return True

        except Exception as e:
            logger.error(f"Failed to configure captive DNS: {e}")
            return False

    async def _remove_captive_dns(self) -> bool:
        """Remove captive portal DNS configuration."""
        try:
            if self._dnsmasq_config_file.exists():
                self._dnsmasq_config_file.unlink()
                logger.info("Removed dnsmasq captive portal config")
            return True
        except Exception as e:
            logger.error(f"Failed to remove captive DNS config: {e}")
            return False

    async def _run_command(self, cmd: list[str]) -> tuple[int | None, str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            return (
                process.returncode,
                stdout.decode("utf-8").strip(),
                stderr.decode("utf-8").strip(),
            )
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return (1, "", str(e))

    async def _detect_wifi_device(self) -> None:
        current_time = time.time()
        if (
            self.wifi_device
            and (current_time - self._device_cache_time) < self._device_cache_timeout
        ):
            return

        returncode, stdout, _ = await self._run_command(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"]
        )

        if returncode != 0:
            logger.error("Failed to get network devices")
            return

        wifi_devices = []
        for line in stdout.split("\n"):
            if not line:
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                device, dev_type, state = parts[0], parts[1], parts[2]
                if dev_type == "wifi":
                    wifi_devices.append((device, state))

        # Priority: connected > disconnected > unavailable
        for device, state in wifi_devices:
            if state == "connected":
                self.wifi_device = device
                break
        else:
            for device, state in wifi_devices:
                if state == "disconnected":
                    self.wifi_device = device
                    break
            else:
                if wifi_devices:
                    self.wifi_device = wifi_devices[0][0]

        self._device_cache_time = current_time

    async def scan_networks(self) -> list[WiFiNetwork]:
        # In AP mode, return cached results
        if self._is_ap_mode:
            logger.info("In AP mode - returning cached network list")
            return self._last_scan_results

        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                return []

        try:
            returncode, _, stderr = await self._run_command(["nmcli", "device", "wifi", "rescan"])
            if returncode != 0:
                logger.warning(f"Network scan failed: {stderr}")
                return self._last_scan_results

            await asyncio.sleep(2)
            returncode, stdout, _ = await self._run_command(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"]
            )

            if returncode != 0:
                return self._last_scan_results

            networks = []
            seen_ssids = set()

            for line in stdout.split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 4:
                    ssid = parts[0]
                    if not ssid or ssid in seen_ssids:
                        continue

                    try:
                        signal = int(parts[1]) if parts[1] else 0
                    except ValueError:
                        signal = 0

                    security = parts[2] if parts[2] else "Open"
                    in_use = parts[3] == "*"

                    networks.append(WiFiNetwork(ssid, signal, security, in_use))
                    seen_ssids.add(ssid)

            networks.sort(key=lambda x: x.signal, reverse=True)
            self._last_scan_results = networks

            return networks

        except Exception as e:
            logger.error(f"Network scan error: {e}")
            return self._last_scan_results

    async def start_ap_mode(
        self, ssid: str, password: str, ip_address: str, channel: int = 6
    ) -> bool:
        if not self._is_ap_mode and not self._last_scan_results:
            logger.info("Performing network scan before entering AP mode...")
            await self.scan_networks()

        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                logger.error("No WiFi device available for AP mode")
                return False

        await self._ensure_dns_port_available()

        # Configure dnsmasq for wildcard DNS (captive portal)
        logger.info("Configuring wildcard DNS for captive portal...")
        dns_configured = await self._configure_captive_dns(ip_address)
        if not dns_configured:
            logger.warning("Failed to configure captive DNS - portal may not work on all devices")

        await self._run_command(["nmcli", "connection", "delete", self.ap_connection_name])
        cmd = [
            "nmcli",
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            self.wifi_device,
            "con-name",
            self.ap_connection_name,
            "autoconnect",
            "no",
            "ssid",
            ssid,
            "mode",
            "ap",
            "802-11-wireless.band",
            "bg",
            "802-11-wireless.channel",
            str(channel),
            "802-11-wireless-security.key-mgmt",
            "wpa-psk",
            "802-11-wireless-security.psk",
            password,
            "ipv4.method",
            "shared",
            "ipv4.addresses",
            f"{ip_address}/24",
            "ipv6.method",
            "disabled",
        ]

        returncode, _, stderr = await self._run_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to create AP: {stderr}")
            return False

        returncode, _, stderr = await self._run_command(
            ["nmcli", "connection", "up", self.ap_connection_name]
        )

        if returncode != 0:
            logger.error(f"Failed to activate AP: {stderr}")
            await self._run_command(["nmcli", "connection", "delete", self.ap_connection_name])
            return False

        self._is_ap_mode = True
        logger.info(f"AP mode started: {ssid}")
        return True

    async def stop_ap_mode(self) -> None:
        await self._run_command(["nmcli", "connection", "down", self.ap_connection_name])
        await asyncio.sleep(1)

        # Remove captive DNS configuration
        await self._remove_captive_dns()

        self._is_ap_mode = False

    async def _validate_network_profile(self, profile_name: str) -> bool:
        """Validate NetworkManager profile integrity and permissions."""

        # Get profile path
        profile_paths = [
            f"/etc/NetworkManager/system-connections/{profile_name}.nmconnection",
            f"/etc/NetworkManager/system-connections/{profile_name}",
        ]

        profile_path = None
        for path in profile_paths:
            if os.path.exists(path):
                profile_path = path
                break

        if not profile_path:
            logger.debug(f"Profile file not found for {profile_name}")
            return True  # Profile managed by NetworkManager only

        try:
            # Check file ownership and permissions
            file_stat = os.stat(profile_path)

            # Should be owned by root
            if file_stat.st_uid != 0:
                logger.warning(
                    f"Profile {profile_name} not owned by root (uid: {file_stat.st_uid})"
                )
                return False

            # Should have 0600 permissions (only root can read/write)
            expected_mode = 0o600
            actual_mode = stat.S_IMODE(file_stat.st_mode)
            if actual_mode != expected_mode:
                logger.warning(
                    f"Profile {profile_name} has insecure permissions: {oct(actual_mode)}"
                )
                return False

            # Check for suspicious content
            with open(profile_path) as f:
                content = f.read()

                # Check for suspicious scripts or commands
                suspicious_patterns = ["script=", "exec=", "system(", "$(", "`", "|", "&&", ";"]

                for pattern in suspicious_patterns:
                    if pattern in content:
                        logger.warning(
                            f"Profile {profile_name} contains suspicious pattern: {pattern}"
                        )
                        return False

            logger.debug(f"Profile {profile_name} validation passed")
            return True

        except Exception as e:
            logger.error(f"Failed to validate profile {profile_name}: {e}")
            return False

    def _validate_ssid(self, ssid: str) -> bool:
        """Validate SSID to prevent injection attacks."""

        # Check length (WiFi spec: 1-32 chars)
        if not ssid or len(ssid) > 32:
            logger.error(f"Invalid SSID length: {len(ssid)}")
            return False

        # Allow only safe characters: alphanumeric, spaces, hyphens, underscores, dots
        # This regex prevents shell metacharacters and control characters
        safe_ssid_pattern = re.compile(r"^[a-zA-Z0-9\s\-_.]+$")
        if not safe_ssid_pattern.match(ssid):
            logger.error(f"SSID contains invalid characters: {ssid}")
            return False

        # Check for suspicious patterns that might indicate injection attempts
        dangerous_patterns = [
            "$",
            "`",
            ";",
            "|",
            "&",
            ">",
            "<",
            "(",
            ")",
            "{",
            "}",
            "[",
            "]",
            "\\",
            '"',
            "'",
            "\n",
            "\r",
            "\t",
        ]
        for pattern in dangerous_patterns:
            if pattern in ssid:
                logger.error(f"SSID contains potentially dangerous character: {pattern}")
                return False

        return True

    async def connect_to_network(self, ssid: str, password: str | None) -> bool:
        # Validate SSID to prevent injection attacks
        if not self._validate_ssid(ssid):
            logger.error(f"SSID validation failed for: {ssid}")
            return False

        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                logger.error("No WiFi device available")
                return False

        await self.stop_ap_mode()

        # Check if connection profile already exists
        returncode, stdout, _ = await self._run_command(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"]
        )

        profile_exists = False
        if returncode == 0:
            for line in stdout.split("\n"):
                if line.strip():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[0] == ssid and "wireless" in parts[1]:
                        profile_exists = True
                        logger.info(f"Found existing connection profile for {ssid}")
                        break

        # If profile exists, try to connect with it first
        if profile_exists:
            # Validate profile integrity before using
            if not await self._validate_network_profile(ssid):
                logger.warning(f"Profile validation failed for {ssid}, recreating")
                await self._run_command(["nmcli", "connection", "delete", ssid])
                profile_exists = False
            else:
                logger.info(f"Attempting to connect with existing profile: {ssid}")
                # Use the original SSID for nmcli commands (they handle escaping internally)
                returncode, _, stderr = await self._run_command(["nmcli", "connection", "up", ssid])

            if profile_exists and returncode == 0:
                # Successfully connected with existing profile
                await asyncio.sleep(3)
                connection_info = await self.get_connection_info()
                if connection_info:
                    self._is_ap_mode = False
                    logger.info(f"Connected to {ssid} using existing profile")
                    return True
            else:
                # Existing profile failed, delete it and create new one
                logger.warning(f"Failed to connect with existing profile: {stderr}")
                await self._run_command(["nmcli", "connection", "delete", ssid])
                profile_exists = False

        # Create new connection profile if it doesn't exist or failed
        if not profile_exists:
            if password:
                # Validate password if provided
                if len(password) < 8 or len(password) > 63:
                    logger.error(f"Invalid WPA password length: {len(password)}")
                    return False

                cmd = [
                    "nmcli",
                    "connection",
                    "add",
                    "type",
                    "wifi",
                    "con-name",
                    ssid,  # Use original SSID
                    "ifname",
                    self.wifi_device,
                    "ssid",
                    ssid,
                    "802-11-wireless-security.key-mgmt",
                    "wpa-psk",
                    "802-11-wireless-security.psk",
                    password,
                ]
            else:
                cmd = [
                    "nmcli",
                    "connection",
                    "add",
                    "type",
                    "wifi",
                    "con-name",
                    ssid,  # Use original SSID
                    "ifname",
                    self.wifi_device,
                    "ssid",
                    ssid,
                ]

            returncode, _, stderr = await self._run_command(cmd)
            if returncode != 0:
                logger.error(f"Failed to create connection profile: {stderr}")
                return False

            returncode, _, stderr = await self._run_command(["nmcli", "connection", "up", ssid])

            if returncode != 0:
                logger.error(f"Failed to connect: {stderr}")
                await self._run_command(["nmcli", "connection", "delete", ssid])
                return False

        await asyncio.sleep(3)
        connection_info = await self.get_connection_info()
        if connection_info:
            self._is_ap_mode = False

        return connection_info is not None

    async def disconnect_from_network(self) -> None:
        if not self.wifi_device:
            return

        returncode, stdout, _ = await self._run_command(
            ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", self.wifi_device]
        )

        if returncode == 0:
            for line in stdout.split("\n"):
                if line.startswith("GENERAL.CONNECTION:"):
                    connection = line.split(":", 1)[1].strip()
                    if connection and connection != "--":
                        await self._run_command(["nmcli", "connection", "down", connection])
                        logger.info(f"Disconnected from: {connection}")
                    break

    async def get_connection_info(self) -> dict[str, str] | None:
        if not self.wifi_device:
            return None

        returncode, stdout, _ = await self._run_command(
            [
                "nmcli",
                "-t",
                "-f",
                "GENERAL.CONNECTION,IP4.ADDRESS,GENERAL.STATE",
                "device",
                "show",
                self.wifi_device,
            ]
        )

        if returncode != 0:
            return None

        info = {}
        connection_name = None
        for line in stdout.split("\n"):
            if line.startswith("GENERAL.CONNECTION:"):
                connection = line.split(":", 1)[1].strip()
                if connection and connection != "--":
                    connection_name = connection
            elif line.startswith("IP4.ADDRESS"):
                ip_info = line.split(":", 1)[1].strip()
                if "/" in ip_info:
                    info["ip_address"] = ip_info.split("/")[0]

        # Check if this is our AP connection
        if connection_name == self.ap_connection_name:
            # This is our AP mode, not a regular network connection
            logger.debug(f"Detected AP mode connection: {connection_name}")
            return None

        # For regular connections, get the actual SSID
        if connection_name:
            # Get the actual SSID from the connection profile
            returncode, stdout, _ = await self._run_command(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "802-11-wireless.ssid",
                    "connection",
                    "show",
                    connection_name,
                ]
            )
            if returncode == 0:
                for line in stdout.split("\n"):
                    if line.startswith("802-11-wireless.ssid:"):
                        ssid = line.split(":", 1)[1].strip()
                        if ssid:
                            info["ssid"] = ssid
                            break

        if "ssid" in info and "ip_address" in info:
            return info

        return None

    async def is_in_ap_mode(self) -> bool:
        """Check if currently running in AP mode."""
        if not self.wifi_device:
            return False

        # Check if our AP connection is active
        returncode, stdout, _ = await self._run_command(
            [
                "nmcli",
                "-t",
                "-f",
                "GENERAL.CONNECTION",
                "device",
                "show",
                self.wifi_device,
            ]
        )

        if returncode == 0:
            for line in stdout.split("\n"):
                if line.startswith("GENERAL.CONNECTION:"):
                    connection = line.split(":", 1)[1].strip()
                    if connection == self.ap_connection_name:
                        return True

        return False

    async def is_connected_to_network(self, ssid: str | None = None) -> bool:
        """Check if currently connected to a WiFi network (optionally a specific SSID)."""
        connection_info = await self.get_connection_info()
        if not connection_info:
            return False

        current_ssid = connection_info.get("ssid")
        if not current_ssid:
            return False

        # If specific SSID requested, check if it matches
        if ssid:
            return current_ssid == ssid

        # Otherwise just check if we're connected to any network
        return True

    async def reconnect_to_saved_network(self, ssid: str) -> bool:
        """Try to reconnect to a previously saved network connection."""
        # Validate SSID to prevent injection attacks
        if not self._validate_ssid(ssid):
            logger.error(f"SSID validation failed for reconnection: {ssid}")
            return False

        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                logger.error("No WiFi device available for reconnection")
                return False

        # First check if we're already connected to this network
        if await self.is_connected_to_network(ssid):
            logger.info(f"Already connected to {ssid}")
            return True

        logger.info(f"Attempting to reconnect to saved network: {ssid}")

        # Check if the connection profile exists
        returncode, stdout, _ = await self._run_command(
            ["nmcli", "-t", "-f", "NAME", "connection", "show"]
        )

        if returncode != 0:
            logger.error("Failed to list network connections")
            return False

        connection_exists = False
        for line in stdout.split("\n"):
            if line.strip() == ssid:
                connection_exists = True
                break

        if not connection_exists:
            logger.info(f"No saved connection profile for {ssid}")
            return False

        # Try to activate the existing connection
        returncode, _, stderr = await self._run_command(["nmcli", "connection", "up", ssid])

        if returncode != 0:
            logger.error(f"Failed to reconnect to {ssid}: {stderr}")
            return False

        # Wait for connection to establish
        await asyncio.sleep(3)

        # Verify connection
        connection_info = await self.get_connection_info()
        if connection_info and connection_info.get("ssid") == ssid:
            logger.info(f"Successfully reconnected to {ssid}")
            self._is_ap_mode = False
            return True

        logger.warning(f"Reconnection to {ssid} verification failed")
        return False

    async def monitor_events(self) -> None:
        logger.info("Starting NetworkManager event monitor")

        process = await asyncio.create_subprocess_exec(
            "nmcli", "monitor", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            event = line.decode("utf-8").strip()
            logger.debug(f"NetworkManager event: {event}")

            # StateManager callback integration point
