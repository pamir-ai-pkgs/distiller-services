"""NetworkManager wrapper for WiFi operations."""

import asyncio
import logging
import os
import re
import shutil
import stat
import time
from pathlib import Path

import httpx

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
        self._event_callbacks: list = []
        self._last_connection_error: str = ""  # Store last connection error for error parsing

    async def initialize(self) -> None:
        await self._detect_wifi_device()
        if self.wifi_device:
            logger.info(f"WiFi device detected: {self.wifi_device}")
        else:
            logger.warning("No WiFi device detected")

    def on_network_event(self, callback):
        """Register a callback for network events.

        Args:
            callback: Async function(event_type: str, details: dict) to call on events
        """
        self._event_callbacks.append(callback)

    async def _trigger_event(self, event_type: str, details: dict = None):
        """Trigger all registered event callbacks."""
        if details is None:
            details = {}

        for callback in self._event_callbacks:
            try:
                await callback(event_type, details)
            except Exception as e:
                logger.error(f"Error in event callback: {e}", exc_info=True)

    async def _ensure_dns_port_available(self) -> None:
        """Stop conflicting DNS services so NetworkManager's dnsmasq can start."""

        if shutil.which("systemctl") is None:
            return

        for service in ("dnsmasq",):
            returncode, _, _ = await self._run_command(
                ["systemctl", "is-active", "--quiet", service]
            )

            if returncode == 0:
                logger.warning(f"Stopping conflicting DNS service '{service}' to free port 53")
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

    def _parse_connection_error(self, stderr: str) -> str:
        """Convert technical nmcli errors to user-friendly messages."""
        # All patterns are lowercase since we lowercase stderr for comparison
        error_map = {
            "secrets were required": "Incorrect password",
            "no network with ssid": "Network not found or out of range",
            "timeout was reached": "Connection timeout - weak signal",
            "base network connection was interrupted": "Network interference detected",
            "failed to activate": "Unable to activate connection",
            "ip configuration could not be reserved": "DHCP timeout - network busy",
        }

        stderr_lower = stderr.lower()
        for pattern, message in error_map.items():
            if pattern in stderr_lower:
                return message

        # Return truncated error if no match
        return f"Connection failed: {stderr[:100]}"

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
                    self._last_connection_error = ""  # Clear error on success
                    logger.info(f"Connected to {ssid} using existing profile")
                    return True
            else:
                # Existing profile failed, delete it and create new one
                logger.warning(f"Failed to connect with existing profile: {stderr}")
                self._last_connection_error = stderr  # Store error for parsing
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
                self._last_connection_error = stderr  # Store error for parsing
                return False

            returncode, _, stderr = await self._run_command(["nmcli", "connection", "up", ssid])

            if returncode != 0:
                logger.error(f"Failed to connect: {stderr}")
                self._last_connection_error = stderr  # Store error for parsing
                await self._run_command(["nmcli", "connection", "delete", ssid])
                return False

        await asyncio.sleep(3)
        connection_info = await self.get_connection_info()
        if connection_info:
            self._is_ap_mode = False
            self._last_connection_error = ""  # Clear error on success

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

    async def verify_connectivity(self, timeout: float = 5.0) -> bool:
        """Verify actual network connectivity with internet reachability test.

        Args:
            timeout: Maximum time to wait for verification (seconds)

        Returns:
            True if network is functional, False otherwise
        """
        try:
            # Check if we have a connection
            connection_info = await self.get_connection_info()
            if not connection_info or not connection_info.get("ip_address"):
                logger.debug("No IP address for connectivity verification")
                return False

            # Test internet reachability with ping
            try:
                returncode, stdout, stderr = await asyncio.wait_for(
                    self._run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"]), timeout=timeout
                )
                if returncode == 0:
                    logger.debug("Connectivity verification successful")
                    return True
                else:
                    logger.debug(f"Connectivity verification failed: {stderr}")
                    return False
            except TimeoutError:
                logger.debug("Connectivity verification timed out")
                return False

        except Exception as e:
            logger.error(f"Connectivity verification error: {e}")
            return False

    async def detect_captive_portal(self) -> tuple[bool, str | None]:
        """Detect captive portal by attempting HTTP requests to connectivity check URLs.

        Tests multiple well-known connectivity check endpoints used by different
        operating systems. Captive portals typically intercept these requests and
        return redirects or unexpected content.

        Returns:
            tuple[bool, str | None]: (is_captive_portal, portal_url)
                - is_captive_portal: True if captive portal detected
                - portal_url: URL of detected captive portal (if found)
        """
        # Connectivity check endpoints used by various operating systems
        test_urls = [
            "http://connectivitycheck.gstatic.com/generate_204",  # Android
            "http://captive.apple.com/hotspot-detect.html",  # iOS/macOS
            "http://detectportal.firefox.com/success.txt",  # Firefox
        ]

        for test_url in test_urls:
            try:
                # Make HTTP request without following redirects
                async with httpx.AsyncClient(follow_redirects=False, timeout=5.0) as client:
                    response = await client.get(test_url)

                    # Captive portal indicators:

                    # 1. HTTP 302/307/308 redirect (most common)
                    if response.status_code in [302, 307, 308]:
                        portal_url = response.headers.get("Location")
                        if portal_url:
                            logger.info(f"Captive portal detected via redirect: {portal_url}")
                            return (True, portal_url)
                        else:
                            logger.info("Captive portal detected (redirect without Location)")
                            return (True, test_url)

                    # 2. HTTP 511 Network Authentication Required (RFC 6585)
                    elif response.status_code == 511:
                        logger.info("Captive portal detected via HTTP 511")
                        return (True, test_url)

                    # 3. HTTP 200 but with unexpected content
                    elif response.status_code == 200:
                        # Expected responses for these endpoints
                        expected_responses = {
                            "connectivitycheck.gstatic.com": "",  # 204 or empty body
                            "captive.apple.com": "Success",
                            "detectportal.firefox.com": "success",
                        }

                        # Check if response matches expected content
                        response_text = response.text.strip()
                        expected = None
                        for domain, exp_text in expected_responses.items():
                            if domain in test_url:
                                expected = exp_text
                                break

                        if expected is not None and expected.lower() not in response_text.lower():
                            logger.info(
                                f"Captive portal detected via unexpected content: "
                                f"got '{response_text[:100]}' instead of '{expected}'"
                            )
                            return (True, test_url)

                    # 4. HTTP 204 No Content - this is what we expect for normal internet
                    elif response.status_code == 204:
                        logger.debug(f"Connectivity check passed: {test_url}")
                        return (False, None)

            except httpx.TimeoutException:
                logger.debug(f"Connectivity check timeout: {test_url}")
                continue
            except httpx.ConnectError:
                logger.debug(f"Connectivity check failed to connect: {test_url}")
                continue
            except Exception as e:
                logger.debug(f"Connectivity check error for {test_url}: {e}")
                continue

        # All tests failed - probably no internet, but not necessarily captive portal
        logger.debug("All connectivity checks failed - no internet or network issue")
        return (False, None)

    async def reconnect_to_saved_network(self, ssid: str) -> bool:
        """Try to reconnect to a previously saved network connection.

        Returns False if profile is stale (wrong password) or doesn't exist,
        forcing fallback to AP mode where user can enter new password.
        """
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
            # Check if this is a stale password error
            if "secrets were required" in stderr.lower():
                logger.warning(f"Stale password detected for {ssid}, deleting profile")
                # Delete the stale profile
                await self._run_command(["nmcli", "connection", "delete", ssid])
                logger.info(
                    f"Deleted stale profile for {ssid} - user will need to re-enter password"
                )
                return False

            logger.error(f"Failed to reconnect to {ssid}: {self._parse_connection_error(stderr)}")
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
        """Monitor NetworkManager events and trigger callbacks on relevant changes.

        Monitors for:
        - Connectivity changes (full, limited, none)
        - Device state changes (disconnected, unavailable, disconnecting)
        - Connection state changes (deactivated, deactivating)
        """
        logger.info("Starting NetworkManager event monitor")

        while True:
            try:
                process = await asyncio.create_subprocess_exec(
                    "nmcli",
                    "monitor",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                while True:
                    line = await process.stdout.readline()
                    if not line:
                        logger.warning("NetworkManager monitor process ended, restarting...")
                        break

                    event = line.decode("utf-8").strip()
                    if not event:
                        continue

                    logger.debug(f"NetworkManager event: {event}")

                    # Parse connectivity changes
                    if "connectivity is now" in event.lower():
                        if "none" in event.lower():
                            logger.warning("Network connectivity lost")
                            await self._trigger_event(
                                "connectivity_lost", {"reason": "no_connectivity"}
                            )
                        elif "limited" in event.lower():
                            logger.warning("Network connectivity limited")
                            await self._trigger_event(
                                "connectivity_degraded", {"reason": "limited_connectivity"}
                            )
                        elif "full" in event.lower():
                            logger.info("Network connectivity restored")
                            await self._trigger_event("connectivity_restored", {})

                    # Parse device state changes
                    if self.wifi_device and self.wifi_device in event:
                        if "disconnected" in event.lower():
                            logger.warning(f"WiFi device {self.wifi_device} disconnected")
                            await self._trigger_event(
                                "device_disconnected", {"device": self.wifi_device}
                            )
                        elif "unavailable" in event.lower():
                            logger.warning(f"WiFi device {self.wifi_device} unavailable")
                            await self._trigger_event(
                                "device_unavailable", {"device": self.wifi_device}
                            )

                    # Parse connection state changes
                    if "deactivating" in event.lower() or "deactivated" in event.lower():
                        # Extract connection name if present
                        connection_match = re.search(r"'([^']+)'", event)
                        connection_name = (
                            connection_match.group(1) if connection_match else "unknown"
                        )
                        if connection_name != self.ap_connection_name:
                            logger.warning(f"Connection {connection_name} deactivated")
                            await self._trigger_event(
                                "connection_deactivated", {"connection": connection_name}
                            )

            except Exception as e:
                logger.error(f"NetworkManager monitor error: {e}", exc_info=True)

            # Wait before restarting monitor
            logger.info("Restarting NetworkManager event monitor in 5 seconds...")
            await asyncio.sleep(5)
