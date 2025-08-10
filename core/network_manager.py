"""NetworkManager wrapper for WiFi operations."""

import asyncio
import logging

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
        self._device_cache_time = 0
        self._device_cache_timeout = 300
        self._is_ap_mode = False
        self._last_scan_results = []
        self.ap_connection_name = "Distiller-AP"
        self.client_connection_prefix = "wifi-"

    async def initialize(self) -> None:
        await self._detect_wifi_device()
        if self.wifi_device:
            logger.info(f"WiFi device detected: {self.wifi_device}")
        else:
            logger.warning("No WiFi device detected")

    async def _run_command(self, cmd: list[str]) -> tuple[int, str, str]:
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
        import time

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

    async def start_ap_mode(self, ssid: str, password: str, ip_address: str) -> bool:
        if not self._is_ap_mode and not self._last_scan_results:
            logger.info("Performing network scan before entering AP mode...")
            await self.scan_networks()

        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                logger.error("No WiFi device available for AP mode")
                return False

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
            "6",
            "802-11-wireless-security.key-mgmt",
            "wpa-psk",
            "802-11-wireless-security.psk",
            password,
            "ipv4.method",
            "shared",
            "ipv4.addresses",
            f"{ip_address}/24",
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
        self._is_ap_mode = False

    async def connect_to_network(self, ssid: str, password: str | None) -> bool:
        if not self.wifi_device:
            await self._detect_wifi_device()
            if not self.wifi_device:
                logger.error("No WiFi device available")
                return False

        await self.stop_ap_mode()
        connection_name = f"{self.client_connection_prefix}{ssid}"
        await self._run_command(["nmcli", "connection", "delete", connection_name])

        if password:
            cmd = [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "con-name",
                connection_name,
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
                connection_name,
                "ifname",
                self.wifi_device,
                "ssid",
                ssid,
            ]

        returncode, _, stderr = await self._run_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to create connection profile: {stderr}")
            return False

        returncode, _, stderr = await self._run_command(
            ["nmcli", "connection", "up", connection_name]
        )

        if returncode != 0:
            logger.error(f"Failed to connect: {stderr}")
            await self._run_command(["nmcli", "connection", "delete", connection_name])
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
        for line in stdout.split("\n"):
            if line.startswith("GENERAL.CONNECTION:"):
                connection = line.split(":", 1)[1].strip()
                if connection and connection != "--":
                    if connection.startswith(self.client_connection_prefix):
                        info["ssid"] = connection[len(self.client_connection_prefix) :]
                    else:
                        info["ssid"] = connection
            elif line.startswith("IP4.ADDRESS"):
                ip_info = line.split(":", 1)[1].strip()
                if "/" in ip_info:
                    info["ip_address"] = ip_info.split("/")[0]
            elif line.startswith("GENERAL.STATE:"):
                state = line.split(":", 1)[1].strip()
                if "100" in state:
                    info["connected"] = True

        if "ssid" in info and "ip_address" in info:
            return info

        return None

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
