"""
Pinggy tunnel service for remote access.
"""

import asyncio
import logging
import re

from core.config import Settings
from core.state import ConnectionState, StateManager

logger = logging.getLogger(__name__)


class TunnelService:
    def __init__(self, settings: Settings, state_manager: StateManager):
        self.settings = settings
        self.state_manager = state_manager
        self.process: asyncio.subprocess.Process | None = None
        self.current_url: str | None = None
        self._running = False
        self._refresh_task: asyncio.Task | None = None
        self._retry_count = 0
        self._max_retries = settings.tunnel_max_retries
        self._retry_delay = settings.tunnel_retry_delay

    async def check_network_connectivity(self) -> bool:
        """Check if network is connected (aligned with commit approach)."""
        state = self.state_manager.get_state()
        if state.connection_state == ConnectionState.CONNECTED:
            if state.network_info and state.network_info.ip_address:
                logger.info(
                    f"Network connected: {state.network_info.ssid} ({state.network_info.ip_address})"
                )
                return True
        logger.debug("No network connectivity")
        return False

    async def run(self):
        """Main tunnel service loop."""
        self._running = True
        logger.info("Tunnel service started")

        # Give WiFi setup service time to complete (as in commit)
        logger.info("Waiting 60 seconds for WiFi setup to complete...")
        await asyncio.sleep(60)

        while self._running:
            try:
                # Check network connectivity first (as in commit)
                if not await self.check_network_connectivity():
                    logger.warning("No network connectivity, waiting...")
                    await asyncio.sleep(30)
                    continue

                # Start tunnel if not running
                if not self.process or self.process.returncode is not None:
                    await self.start_tunnel()

                # Wait before checking again
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Tunnel service error: {e}")
                await asyncio.sleep(30)

    async def start_tunnel(self):
        """Start SSH tunnel through Pinggy with retry logic."""
        if not self.settings.tunnel_enabled:
            logger.info("Tunnel service disabled in settings")
            return

        while self._retry_count < self._max_retries:
            try:
                logger.info(
                    f"Starting Pinggy tunnel... (attempt {self._retry_count + 1}/{self._max_retries})"
                )

                # Build SSH command for Pinggy tunnel
                # Note: Pinggy.io accepts anonymous connections without authentication
                cmd = [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",  # Required for automatic connections
                    "-o",
                    "ServerAliveInterval=30",
                    "-o",
                    "ServerAliveCountMax=3",
                    "-o",
                    "UserKnownHostsFile=/dev/null",  # Don't save host keys
                    "-o",
                    "LogLevel=ERROR",  # Reduce log verbosity
                    "-R",
                    f"0:localhost:{self.settings.web_port}",
                    "-p",
                    str(self.settings.tunnel_ssh_port),
                    "a.pinggy.io",
                ]

                logger.info("Starting anonymous Pinggy tunnel (will get random unique URL)")
                logger.debug(f"SSH command: {' '.join(cmd)}")

                # Start SSH process with unbuffered output and no stdin
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,  # Prevent interactive prompts
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    bufsize=0,  # Unbuffered for immediate output
                )

                # Start output reader task
                asyncio.create_task(self._read_tunnel_output())

                # Immediately check for early errors in stderr
                try:
                    stderr_data = await asyncio.wait_for(
                        self.process.stderr.read(1024), timeout=2.0
                    )
                    if stderr_data:
                        error_msg = stderr_data.decode("utf-8").strip()
                        logger.error(f"Tunnel stderr during startup: {error_msg}")
                except TimeoutError:
                    # No immediate stderr output is actually good
                    pass

                # Wait for tunnel to establish (as in commit)
                logger.info("Waiting for tunnel to establish...")
                await asyncio.sleep(5)

                # Check if process is still running
                if self.process.returncode is not None:
                    # Process exited, likely auth failure
                    self._retry_count += 1
                    logger.warning(f"Tunnel process exited with code {self.process.returncode}")

                    if self._retry_count < self._max_retries:
                        logger.warning(
                            f"Failed to establish tunnel, retrying in {self._retry_delay} seconds"
                        )
                        await asyncio.sleep(self._retry_delay)
                        continue
                    else:
                        logger.error("Max retries reached, tunnel service failed")
                        self.process = None
                        return

                # Success - reset retry count
                self._retry_count = 0

                # Start refresh task
                if self._refresh_task:
                    self._refresh_task.cancel()
                self._refresh_task = asyncio.create_task(self._refresh_tunnel())

                logger.info("Tunnel process started successfully")
                return

            except Exception as e:
                logger.error(f"Failed to start tunnel: {e}")
                self._retry_count += 1

                if self._retry_count < self._max_retries:
                    logger.warning(
                        f"Failed to establish tunnel, retrying in {self._retry_delay} seconds"
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error("Max retries reached, tunnel service failed")
                    self.process = None
                    return

    async def stop_tunnel(self):
        """Stop SSH tunnel."""
        try:
            if self._refresh_task:
                self._refresh_task.cancel()
                self._refresh_task = None

            if self.process and self.process.returncode is None:
                logger.info("Stopping tunnel...")
                self.process.terminate()

                # Wait for graceful shutdown
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    logger.warning("Tunnel didn't stop gracefully, killing...")
                    self.process.kill()
                    await self.process.wait()

                self.process = None
                self.current_url = None
                self._retry_count = 0  # Reset retry count

                # Clear tunnel URL in state
                await self.state_manager.update_state(tunnel_url=None)

                logger.info("Tunnel stopped")

        except Exception as e:
            logger.error(f"Error stopping tunnel: {e}")

    async def _read_tunnel_output(self):
        """Read and parse tunnel output for URL."""
        if not self.process:
            return

        try:
            url_patterns = [
                r"https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                r"http://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                r"https://[a-zA-Z0-9\-]+\.free\.pinggy\.link",
                r"http://[a-zA-Z0-9\-]+\.free\.pinggy\.link",
            ]

            # Read stdout line by line
            while self.process and self.process.returncode is None:
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)

                    if not line:
                        break

                    text = line.decode("utf-8").strip()
                    if text:
                        logger.debug(f"Tunnel output: {text}")

                        # Look for URL
                        for pattern in url_patterns:
                            match = re.search(pattern, text)
                            if match:
                                url = match.group(0)
                                if not url.startswith("http"):
                                    url = f"https://{url}"

                                if url != self.current_url:
                                    self.current_url = url
                                    logger.info(f"New unique Pinggy tunnel URL: {url}")

                                    # Update state with tunnel URL
                                    await self.state_manager.update_state(tunnel_url=url)
                                break

                except TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error reading tunnel output: {e}")
                    break

            # Also read stderr for errors
            if self.process and self.process.stderr:
                try:
                    stderr = await self.process.stderr.read()
                    if stderr:
                        logger.error(f"Tunnel stderr: {stderr.decode('utf-8')}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Tunnel output reader error: {e}")

    async def _refresh_tunnel(self):
        """Periodically refresh tunnel before expiry (rotation as in commit)."""
        try:
            while self._running and self.process:
                # Wait for refresh interval (55 minutes before 1 hour expiry)
                logger.info(
                    f"Next tunnel refresh in {self.settings.tunnel_refresh_interval} seconds"
                )
                await asyncio.sleep(self.settings.tunnel_refresh_interval)

                if not self._running:
                    break

                logger.info("Refreshing tunnel (rotation)...")

                # Stop current tunnel
                await self.stop_tunnel()

                # Wait a moment
                await asyncio.sleep(5)

                # Check connectivity and restart tunnel
                if await self.check_network_connectivity():
                    await self.start_tunnel()
                else:
                    logger.warning("Lost connectivity during refresh, will retry when connected")

        except asyncio.CancelledError:
            logger.debug("Refresh task cancelled")
        except Exception as e:
            logger.error(f"Tunnel refresh error: {e}")

    async def stop(self):
        """Stop the tunnel service."""
        self._running = False

        if self._refresh_task:
            self._refresh_task.cancel()

        await self.stop_tunnel()

        logger.info("Tunnel service stopped")
