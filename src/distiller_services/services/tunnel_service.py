"""
Tunnel service with FRP primary and Pinggy fallback support.
"""

import asyncio
import logging
import re
from enum import Enum
from pathlib import Path

from distiller_services.core.config import Settings
from distiller_services.core.state import ConnectionState, StateManager

logger = logging.getLogger(__name__)


class TunnelProvider(Enum):
    """Tunnel provider types."""

    FRP = "frp"
    PINGGY = "pinggy"


class TunnelService:
    def __init__(self, settings: Settings, state_manager: StateManager, network_manager=None):
        self.settings = settings
        self.state_manager = state_manager
        self.network_manager = network_manager
        self.process: asyncio.subprocess.Process | None = None
        self.current_url: str | None = None
        self.current_provider: TunnelProvider | None = None
        self._running = False
        self._refresh_task: asyncio.Task | None = None
        self._frp_monitor_task: asyncio.Task | None = None
        self._retry_count = 0
        self._max_retries = settings.tunnel_max_retries
        self._retry_delay = settings.tunnel_retry_delay

        # Track network state for logging changes only
        self._last_network_state: dict[str, str | None] = {
            "ssid": None,
            "ip_address": None,
            "connected": False,
        }

        # Device serial for FRP
        self._device_serial: str | None = None
        self._init_device_serial()

        # Pinggy tunnel type based on token
        if settings.pinggy_access_token:
            self.pinggy_refresh_interval = 86400  # 24 hours for persistent
            self.pinggy_tunnel_type = "persistent"
        else:
            self.pinggy_refresh_interval = settings.tunnel_refresh_interval
            self.pinggy_tunnel_type = "free"

    def _init_device_serial(self):
        """Initialize device serial from config or device.env file."""
        # First check if serial is configured
        if self.settings.device_serial:
            self._device_serial = self.settings.device_serial
            logger.info(f"Using configured device serial: {self._device_serial}")
            return

        # Try to read from device.env file
        try:
            env_path = Path(self.settings.device_env_path)
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("SERIAL="):
                            self._device_serial = line.split("=", 1)[1].strip()
                            logger.info(f"Found device serial in {env_path}: {self._device_serial}")
                            return
        except Exception as e:
            logger.warning(
                f"Failed to read device serial from {self.settings.device_env_path}: {e}"
            )

        logger.info("No device serial found, will use Pinggy only")

    async def check_network_connectivity(self) -> bool:
        """Check if network is connected."""
        state = self.state_manager.get_state()
        if state.connection_state == ConnectionState.CONNECTED:
            if state.network_info and state.network_info.ip_address:
                # Only log at INFO level when state changes
                current_ssid = state.network_info.ssid
                current_ip = state.network_info.ip_address

                if (
                    not self._last_network_state["connected"]
                    or self._last_network_state["ssid"] != current_ssid
                    or self._last_network_state["ip_address"] != current_ip
                ):
                    logger.info(f"Network connected: {current_ssid} ({current_ip})")
                    self._last_network_state["connected"] = True
                    self._last_network_state["ssid"] = current_ssid
                    self._last_network_state["ip_address"] = current_ip
                else:
                    logger.debug(f"Network still connected: {current_ssid} ({current_ip})")

                return True

        # Network not connected
        if self._last_network_state["connected"]:
            logger.info("Network disconnected")
            self._last_network_state["connected"] = False
            self._last_network_state["ssid"] = None
            self._last_network_state["ip_address"] = None
        else:
            logger.debug("No network connectivity")

        return False

    async def check_frp_health(self) -> bool:
        """Check if FRP service is healthy using systemctl."""
        if not self._device_serial:
            return False

        try:
            cmd = ["systemctl", "is-active", self.settings.frp_service_name]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()

            is_active = stdout.decode().strip() == "active"
            if is_active:
                logger.debug(f"FRP service {self.settings.frp_service_name} is active")
            return is_active

        except Exception as e:
            logger.error(f"Failed to check FRP health: {e}")
            return False

    def get_frp_url(self) -> str | None:
        """Generate FRP URL from device serial."""
        if not self._device_serial:
            return None
        return f"https://{self._device_serial}.{self.settings.devices_domain}"

    async def start_frp_tunnel(self) -> bool:
        """Start FRP tunnel (just verify service and set URL)."""
        if not self._device_serial:
            logger.info("No device serial, cannot use FRP")
            return False

        logger.info("Checking FRP service status...")

        # Check if FRP service is running
        if await self.check_frp_health():
            self.current_provider = TunnelProvider.FRP
            self.current_url = self.get_frp_url()
            logger.info(f"FRP tunnel active: {self.current_url}")

            # Update state with FRP URL
            await self.state_manager.update_state(
                tunnel_url=self.current_url, tunnel_provider="frp"
            )
            return True
        else:
            logger.warning(f"FRP service {self.settings.frp_service_name} is not active")
            return False

    async def start_pinggy_tunnel(self):
        """Start SSH tunnel through Pinggy."""
        try:
            logger.info("Starting Pinggy tunnel...")

            # Build SSH command for Pinggy tunnel
            if self.settings.pinggy_access_token:
                # Persistent tunnel with token
                cmd = [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "ServerAliveInterval=30",
                    "-o",
                    "ServerAliveCountMax=3",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "LogLevel=ERROR",
                    "-R",
                    "0:localhost:3000",
                    "-p",
                    str(self.settings.tunnel_ssh_port),
                    f"{self.settings.pinggy_access_token}@a.pinggy.io",
                ]
                logger.info("[PERSISTENT] Starting persistent Pinggy tunnel with token")
            else:
                # Free plan - anonymous connection
                cmd = [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "ServerAliveInterval=30",
                    "-o",
                    "ServerAliveCountMax=3",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "LogLevel=ERROR",
                    "-R",
                    "0:localhost:3000",
                    "-p",
                    str(self.settings.tunnel_ssh_port),
                    "a.pinggy.io",
                ]
                logger.info("[FREE] Starting anonymous Pinggy tunnel")

            # Start SSH process
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                bufsize=0,
            )

            self.current_provider = TunnelProvider.PINGGY

            # Start output reader task
            asyncio.create_task(self._read_pinggy_output())

            # Wait for tunnel to establish
            logger.info("Waiting for Pinggy tunnel to establish...")
            await asyncio.sleep(5)

            # Check if process is still running
            if self.process.returncode is not None:
                logger.error(f"Pinggy process exited with code {self.process.returncode}")
                self.process = None
                return False

            # Start refresh task for Pinggy
            if self._refresh_task:
                self._refresh_task.cancel()
            self._refresh_task = asyncio.create_task(self._refresh_pinggy_tunnel())

            logger.info("Pinggy tunnel started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start Pinggy tunnel: {e}")
            return False

    async def stop_pinggy_tunnel(self):
        """Stop Pinggy SSH tunnel."""
        try:
            if self._refresh_task:
                self._refresh_task.cancel()
                self._refresh_task = None

            if self.process and self.process.returncode is None:
                logger.info("Stopping Pinggy tunnel...")
                self.process.terminate()

                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    logger.warning("Pinggy tunnel didn't stop gracefully, killing...")
                    self.process.kill()
                    await self.process.wait()

                self.process = None
                logger.info("Pinggy tunnel stopped")

        except Exception as e:
            logger.error(f"Error stopping Pinggy tunnel: {e}")

    async def _read_pinggy_output(self):
        """Read and parse Pinggy tunnel output for URL."""
        if not self.process:
            return

        try:
            # URL patterns for Pinggy
            if self.settings.pinggy_access_token:
                # Persistent tunnel URLs
                url_patterns = [
                    r"https://[a-zA-Z0-9\-]+\.pinggy\.link",
                    r"http://[a-zA-Z0-9\-]+\.pinggy\.link",
                    r"https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.pinggy\.link",
                ]
            else:
                # Free tunnel URLs
                url_patterns = [
                    r"https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                    r"http://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                    r"https://[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                ]

            while self.process and self.process.returncode is None:
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)

                    if not line:
                        break

                    text = line.decode("utf-8").strip()
                    if text:
                        logger.debug(f"Pinggy output: {text}")

                        # Look for URL
                        for pattern in url_patterns:
                            match = re.search(pattern, text)
                            if match:
                                url = match.group(0)
                                if not url.startswith("http"):
                                    url = f"https://{url}"

                                if url != self.current_url:
                                    self.current_url = url
                                    logger.info(f"New Pinggy tunnel URL: {url}")

                                    # Update state with Pinggy URL
                                    await self.state_manager.update_state(
                                        tunnel_url=url, tunnel_provider="pinggy"
                                    )
                                break

                except TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error reading Pinggy output: {e}")
                    break

        except Exception as e:
            logger.error(f"Pinggy output reader error: {e}")

    async def _refresh_pinggy_tunnel(self):
        """Periodically refresh Pinggy tunnel before expiry."""
        try:
            while self._running and self.current_provider == TunnelProvider.PINGGY:
                # Wait for refresh interval
                hours = self.pinggy_refresh_interval // 3600
                minutes = (self.pinggy_refresh_interval % 3600) // 60
                time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                logger.info(f"Next Pinggy refresh in {time_str}")
                await asyncio.sleep(self.pinggy_refresh_interval)

                if not self._running:
                    break

                logger.info("Refreshing Pinggy tunnel...")

                # Stop current tunnel
                await self.stop_pinggy_tunnel()
                await asyncio.sleep(5)

                # Restart if still on Pinggy
                if self.current_provider == TunnelProvider.PINGGY:
                    if await self.check_network_connectivity():
                        await self.start_pinggy_tunnel()

        except asyncio.CancelledError:
            logger.debug("Pinggy refresh task cancelled")
        except Exception as e:
            logger.error(f"Pinggy refresh error: {e}")

    async def _monitor_frp_recovery(self):
        """Monitor FRP health while using Pinggy and switch back when available."""
        try:
            while self._running and self.current_provider == TunnelProvider.PINGGY:
                await asyncio.sleep(60)  # Check every 60 seconds

                if await self.check_frp_health():
                    logger.info("FRP service is now active, switching from Pinggy to FRP")

                    # Stop Pinggy
                    await self.stop_pinggy_tunnel()

                    # Switch to FRP
                    if await self.start_frp_tunnel():
                        logger.info("Successfully switched to FRP tunnel")
                        break

        except asyncio.CancelledError:
            logger.debug("FRP monitor task cancelled")
        except Exception as e:
            logger.error(f"FRP monitor error: {e}")

    async def start_tunnel(self):
        """Start tunnel service with FRP primary and Pinggy fallback."""
        if not self.settings.tunnel_enabled:
            logger.info("Tunnel service disabled in settings")
            return

        # Try FRP first if we have a serial
        if self._device_serial and self.settings.tunnel_provider == "frp":
            if await self.start_frp_tunnel():
                return  # FRP is working
            else:
                logger.info("FRP not available, falling back to Pinggy")

        # Fallback to Pinggy
        if await self.start_pinggy_tunnel():
            # Start monitoring FRP for recovery if we have a serial
            if self._device_serial and self.settings.tunnel_provider == "frp":
                if self._frp_monitor_task:
                    self._frp_monitor_task.cancel()
                self._frp_monitor_task = asyncio.create_task(self._monitor_frp_recovery())
        else:
            # Both failed - clear tunnel URL and show error
            logger.error("Both FRP and Pinggy failed to start")
            self.current_url = None
            self.current_provider = None
            await self.state_manager.update_state(tunnel_url=None, tunnel_provider=None)

    async def run(self):
        """Main tunnel service loop."""
        self._running = True
        logger.info("Tunnel service started")

        consecutive_failures = 0
        backoff_delay = 5

        while self._running:
            try:
                # Check network connectivity
                if not await self.check_network_connectivity():
                    # Lost connectivity - clear tunnel URL
                    if self.current_url:
                        logger.warning("Lost network connectivity, clearing tunnel URL")
                        self.current_url = None
                        await self.state_manager.update_state(tunnel_url=None)

                    # Stop Pinggy if running
                    if self.current_provider == TunnelProvider.PINGGY:
                        await self.stop_pinggy_tunnel()
                        self.current_provider = None

                    # Reset failure counter when network is down
                    consecutive_failures = 0
                    backoff_delay = 5

                    await asyncio.sleep(5)
                    continue

                # Start tunnel if not running
                if not self.current_url:
                    # Verify actual network before attempting
                    if self.network_manager and await self.network_manager.verify_connectivity():
                        logger.info(f"Starting tunnel (previous failures: {consecutive_failures})")
                        await self.start_tunnel()

                        # Check if start succeeded
                        if self.current_url:
                            # Success - reset counters
                            consecutive_failures = 0
                            backoff_delay = 5
                            logger.info("Tunnel started successfully")
                        else:
                            # Failed - increment and backoff
                            consecutive_failures += 1
                            backoff_delay = min(5 * (2**consecutive_failures), 300)
                            logger.warning(
                                f"Tunnel start failed (attempt {consecutive_failures}), "
                                f"backing off for {backoff_delay}s"
                            )
                            await asyncio.sleep(backoff_delay - 5)
                    else:
                        logger.debug("Network validation failed, skipping tunnel start")
                        consecutive_failures = 0

                elif self.current_provider == TunnelProvider.PINGGY:
                    # Check if Pinggy process is still alive
                    if self.process and self.process.returncode is not None:
                        logger.warning("Pinggy process died")
                        # Verify network before restart
                        if (
                            self.network_manager
                            and await self.network_manager.verify_connectivity()
                        ):
                            logger.info("Network available, restarting tunnel...")
                            self.current_url = None
                        else:
                            logger.debug("Network unavailable, not restarting tunnel")
                            self.current_url = None
                            self.current_provider = None

                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Tunnel service error: {e}")
                await asyncio.sleep(10)

    async def stop(self):
        """Stop the tunnel service."""
        self._running = False

        if self._refresh_task:
            self._refresh_task.cancel()

        if self._frp_monitor_task:
            self._frp_monitor_task.cancel()

        if self.current_provider == TunnelProvider.PINGGY:
            await self.stop_pinggy_tunnel()

        self.current_url = None
        self.current_provider = None
        await self.state_manager.update_state(tunnel_url=None, tunnel_provider=None)

        logger.info("Tunnel service stopped")
