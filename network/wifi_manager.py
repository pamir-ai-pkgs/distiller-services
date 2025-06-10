"""
WiFi Manager for Network Operations

Handles WiFi network scanning, connection, and hotspot management
using NetworkManager via nmcli commands.
"""

import asyncio
import json
import logging
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class NetworkInfo:
    """Network information container"""

    ssid: str
    signal: int
    security: str
    frequency: str
    in_use: bool = False


@dataclass
class ConnectionStatus:
    """Connection status container"""

    connected: bool
    ssid: Optional[str] = None
    interface: Optional[str] = None
    ip_address: Optional[str] = None


class WiFiManagerError(Exception):
    """WiFi Manager specific exceptions"""

    pass


class WiFiManager:
    """Professional WiFi management using NetworkManager"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._hotspot_active = False
        self._hotspot_connection_name = "wifi-setup-hotspot"
        self.hotspot_ssid = None
        self.hotspot_password = None

    async def get_connection_status(self) -> ConnectionStatus:
        """Get current WiFi connection status"""
        try:
            cmd = [
                "nmcli",
                "-t",
                "-f",
                "TYPE,DEVICE,STATE,NAME",
                "connection",
                "show",
                "--active",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            
            self.logger.debug(f"nmcli active connections output: {stdout.decode()}")

            if process.returncode != 0:
                self.logger.debug(f"nmcli error: {stderr.decode()}")
                return ConnectionStatus(connected=False)

            # Parse active connections
            for line in stdout.decode().strip().split("\n"):
                if not line:
                    continue

                parts = line.split(":")
                self.logger.debug(f"Connection line parts: {parts}")
                
                if len(parts) >= 4 and parts[0] == "802-11-wireless":
                    device = parts[1]
                    state = parts[2]
                    connection = parts[3]

                    if state == "activated":
                        # Get the actual SSID from the device info
                        actual_ssid = await self._get_device_ssid(device)
                        # Get IP address
                        ip_address = await self._get_device_ip(device)

                        self.logger.debug(f"Found activated WiFi: device={device}, connection={connection}, actual_ssid={actual_ssid}, ip={ip_address}")

                        return ConnectionStatus(
                            connected=True,
                            ssid=actual_ssid if actual_ssid else connection,
                            interface=device,
                            ip_address=ip_address,
                        )

            return ConnectionStatus(connected=False)

        except Exception as e:
            self.logger.error(f"Status check error: {e}")
            return ConnectionStatus(connected=False)

    async def connect_to_network(self, ssid: str, password: str = "") -> bool:
        """Connect to a WiFi network with optional password

        For single-band devices, temporarily stops hotspot before connecting,
        then handles hotspot restoration based on connection success/failure.
        """
        try:
            self.logger.info(f"Attempting to connect to network: {ssid}")

            # Check if hotspot is active - if so, we need the stop-connect-handle sequence
            if self._hotspot_active:
                self.logger.info("Stopping hotspot for connection attempt")
                return await self._connect_with_hotspot_management(ssid, password)
            else:
                # Normal connection if no hotspot is running
                return await self._perform_network_connection(ssid, password)

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            raise WiFiManagerError(f"Failed to connect to {ssid}: {e}")

    async def _connect_with_hotspot_management(
        self, ssid: str, password: str = ""
    ) -> bool:
        """Perform network connection with hotspot stop-connect-handle sequence for single-band devices"""
        hotspot_ssid = None
        hotspot_password = None

        try:
            # Store hotspot configuration before stopping
            hotspot_ssid = self.hotspot_ssid
            hotspot_password = self.hotspot_password

            self.logger.info("Stopping hotspot for network connection")
            await self.stop_hotspot()
            await asyncio.sleep(3)

            success = await self._perform_network_connection(ssid, password)

            if success:
                self.logger.info(f"Connected to {ssid}")
                return True
            else:
                if hotspot_ssid and hotspot_password:
                    await asyncio.sleep(1)
                    await self.start_hotspot(hotspot_ssid, hotspot_password)
                    self.logger.info("Hotspot restored")
                return False

        except Exception as e:
            # Ensure we try to restart the hotspot even if connection failed
            self.logger.error(f"Error during hotspot-managed connection: {e}")

            if hotspot_ssid and hotspot_password:
                try:
                    await self.start_hotspot(hotspot_ssid, hotspot_password)
                    self.logger.info("Hotspot restored")
                except Exception as restore_error:
                    self.logger.error(f"Failed to restore hotspot: {restore_error}")

            raise WiFiManagerError(
                f"Network connection with hotspot management failed: {e}"
            )

    async def _perform_network_connection(self, ssid: str, password: str = "") -> bool:
        """Perform the actual network connection operation using --ask for reliable authentication"""
        try:
            if password:
                cmd = ["nmcli", "--ask", "dev", "wifi", "connect", ssid]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                password_input = f"{password}\n"
                stdout, stderr = await process.communicate(
                    input=password_input.encode()
                )
            else:
                cmd = ["nmcli", "dev", "wifi", "connect", ssid]
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return True

            error_msg = stderr.decode().strip()

            if "No network with SSID" in error_msg:
                raise WiFiManagerError(
                    f"Network '{ssid}' not found. Please check the network name and ensure it's available."
                )
            elif "Secrets were required" in error_msg and not password:
                raise WiFiManagerError(
                    f"Network '{ssid}' requires a password. Please provide the password."
                )
            elif password and (
                "password" in error_msg.lower()
                or "authentication" in error_msg.lower()
                or "psk" in error_msg.lower()
                or "key-mgmt" in error_msg.lower()
            ):
                raise WiFiManagerError(
                    f"Authentication failed for '{ssid}'. Please check the password."
                )
            else:
                raise WiFiManagerError(f"Connection failed: {error_msg}")

        except Exception as e:
            if isinstance(e, WiFiManagerError):
                raise
            raise WiFiManagerError(f"Network connection failed: {str(e)}")

    async def forget_network(self, ssid: str) -> bool:
        """Forget a saved WiFi network"""
        try:
            cmd = ["nmcli", "connection", "delete", ssid]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode == 0:
                self.logger.info(f"Successfully forgot network: {ssid}")
                return True
            else:
                self.logger.warning(f"Failed to forget network {ssid} (may not exist)")
                return False

        except Exception as e:
            self.logger.error(f"Forget network error: {e}")
            return False

    async def start_hotspot(self, ssid: str, password: str) -> bool:
        """Start WiFi hotspot"""
        try:
            if self._hotspot_active:
                await self.stop_hotspot()

            # Store hotspot configuration for potential restoration
            self.hotspot_ssid = ssid
            self.hotspot_password = password

            self.logger.info(f"Starting hotspot: {ssid}")

            # Create hotspot connection
            cmd = [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "ifname",
                "*",
                "con-name",
                self._hotspot_connection_name,
                "autoconnect",
                "no",
                "ssid",
                ssid,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode != 0:
                raise WiFiManagerError("Failed to create hotspot connection")

            # Configure hotspot settings
            cmds = [
                [
                    "nmcli",
                    "connection",
                    "modify",
                    self._hotspot_connection_name,
                    "802-11-wireless.mode",
                    "ap",
                ],
                [
                    "nmcli",
                    "connection",
                    "modify",
                    self._hotspot_connection_name,
                    "802-11-wireless-security.key-mgmt",
                    "wpa-psk",
                ],
                [
                    "nmcli",
                    "connection",
                    "modify",
                    self._hotspot_connection_name,
                    "802-11-wireless-security.psk",
                    password,
                ],
                [
                    "nmcli",
                    "connection",
                    "modify",
                    self._hotspot_connection_name,
                    "ipv4.method",
                    "shared",
                ],
                [
                    "nmcli",
                    "connection",
                    "modify",
                    self._hotspot_connection_name,
                    "ipv4.addresses",
                    "192.168.4.1/24",
                ],
            ]

            for cmd in cmds:
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

                if process.returncode != 0:
                    await self._cleanup_hotspot_connection()
                    raise WiFiManagerError(
                        f"Failed to configure hotspot: {' '.join(cmd)}"
                    )

            # Activate hotspot
            cmd = ["nmcli", "connection", "up", self._hotspot_connection_name]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode == 0:
                self._hotspot_active = True
                self.logger.info(f"Hotspot '{ssid}' started successfully")
                return True
            else:
                await self._cleanup_hotspot_connection()
                raise WiFiManagerError("Failed to activate hotspot")

        except Exception as e:
            self.logger.error(f"Hotspot start error: {e}")
            await self._cleanup_hotspot_connection()
            raise WiFiManagerError(f"Failed to start hotspot: {e}")

    async def stop_hotspot(self) -> bool:
        """Stop WiFi hotspot"""
        try:
            if not self._hotspot_active:
                return True

            self.logger.info("Stopping hotspot")

            # Deactivate and remove hotspot connection
            cmds = [
                ["nmcli", "connection", "down", self._hotspot_connection_name],
                ["nmcli", "connection", "delete", self._hotspot_connection_name],
            ]

            for cmd in cmds:
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

            self._hotspot_active = False
            self.logger.info("Hotspot stopped successfully")
            return True

        except Exception as e:
            self.logger.error(f"Hotspot stop error: {e}")
            return False

    async def _get_device_ip(self, device: str) -> Optional[str]:
        """Get IP address for a network device"""
        try:
            cmd = ["nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", device]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0:
                for line in stdout.decode().strip().split("\n"):
                    if line.startswith("IP4.ADDRESS"):
                        return line.split(":")[1].split("/")[0]

            return None

        except Exception:
            return None

    async def _get_device_ssid(self, device: str) -> Optional[str]:
        """Get the SSID for a WiFi device by checking which network is in use"""
        try:
            cmd = ["nmcli", "-t", "-f", "IN-USE,SSID", "dev", "wifi"]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0:
                for line in stdout.decode().strip().split("\n"):
                    if line.startswith("*:"):
                        # Extract SSID from the line (format is "*:SSID")
                        ssid = line.split(":", 1)[1]
                        return ssid if ssid else None

            return None

        except Exception:
            return None

    async def _cleanup_hotspot_connection(self):
        """Clean up hotspot connection on error"""
        try:
            cmd = ["nmcli", "connection", "delete", self._hotspot_connection_name]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except Exception:
            pass  # Ignore cleanup errors
