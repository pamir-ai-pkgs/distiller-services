#!/usr/bin/env python3
"""Distiller WiFi Provisioning System."""

import argparse
import asyncio
import logging
import os
import secrets
import socket
import string
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from core.avahi_service import AvahiService
from core.config import Settings, get_settings
from core.network_manager import NetworkManager
from core.state import ConnectionState, NetworkInfo, StateManager
from services.display_service import DisplayService
from services.tunnel_service import TunnelService
from services.web_server import WebServer


def setup_logging(debug: bool = False):
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [
        logging.StreamHandler(sys.stdout),
    ]

    # Add file handler if we have write permissions
    try:
        log_dir = Path("/var/log/distiller")
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_dir / "distiller-wifi.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except (PermissionError, OSError) as e:
        print(f"Warning: Could not create log file: {e}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
    )


setup_logging()

logger = logging.getLogger(__name__)


class DistillerWiFiApp:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.running = False

        self.state_manager = StateManager(self.settings.state_file)
        self.network_manager = NetworkManager()
        self.avahi_service = AvahiService(self.settings.web_port)
        self.web_server = WebServer(self.settings, self.network_manager, self.state_manager)
        self.display_service = DisplayService(self.settings, self.state_manager)
        self.tunnel_service = TunnelService(self.settings, self.state_manager)
        self.tasks = []
        self.server = None

    def generate_ap_password(self) -> str:
        """Generate secure random password for AP mode."""
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(12))

    async def initialize(self):
        logger.info("Initializing Distiller WiFi System...")

        logger.info(f"Device ID: {self.settings.device_id}")
        logger.info(f"mDNS hostname: {self.settings.mdns_fqdn}")
        logger.info(f"AP SSID: {self.settings.ap_ssid}")

        await self.network_manager.initialize()

        # Check if we have a saved network connection to reconnect to
        saved_state = self.state_manager.get_state()
        reconnected = False

        # First, check if we're in AP mode from a previous run
        is_in_ap = await self.network_manager.is_in_ap_mode()
        if is_in_ap:
            logger.info("Detected existing AP mode connection, cleaning up...")
            await self.network_manager.stop_ap_mode()
            # Small delay to ensure cleanup completes
            await asyncio.sleep(1)

        # Now check if we're connected to a regular network
        current_connection = await self.network_manager.get_connection_info()
        if current_connection and current_connection.get("ssid"):
            current_ssid = current_connection.get("ssid")
            logger.info(f"Already connected to network: {current_ssid}")

            # Update state with current connection

            network_info = NetworkInfo(
                ssid=current_ssid,
                ip_address=current_connection.get("ip_address"),
            )
            await self.state_manager.update_state(
                connection_state=ConnectionState.CONNECTED,
                network_info=network_info,
                reset_retry=True,
            )
            reconnected = True

        elif saved_state.network_info and saved_state.network_info.ssid:
            # Not currently connected, but we have a saved network to try
            logger.info(f"Found saved network: {saved_state.network_info.ssid}")
            logger.info("Attempting to reconnect to saved network...")

            # Try to reconnect to the saved network
            reconnected = await self.network_manager.reconnect_to_saved_network(
                saved_state.network_info.ssid
            )

            if reconnected:
                # Update state to connected
                logger.info(f"Successfully reconnected to {saved_state.network_info.ssid}")

                # Get updated connection info
                connection_info = await self.network_manager.get_connection_info()
                if connection_info:
                    network_info = NetworkInfo(
                        ssid=connection_info.get("ssid"),
                        ip_address=connection_info.get("ip_address"),
                    )
                    await self.state_manager.update_state(
                        connection_state=ConnectionState.CONNECTED,
                        network_info=network_info,
                        reset_retry=True,
                    )
            else:
                logger.info("Could not reconnect to saved network, starting AP mode...")

        # Only start AP mode if we're not connected to any network
        if not reconnected:
            # Generate dynamic password for AP mode
            ap_password = self.generate_ap_password()
            logger.info("=" * 50)
            logger.info(f"NEW AP PASSWORD GENERATED: {ap_password}")
            logger.info("=" * 50)

            # Update state with the new password
            await self.state_manager.update_state(ap_password=ap_password)

            logger.info("Starting Access Point mode...")
            success = await self.network_manager.start_ap_mode(
                ssid=self.settings.ap_ssid,
                password=ap_password,
                ip_address=self.settings.ap_ip,
            )

            if success:
                await self.state_manager.update_state(connection_state=ConnectionState.AP_MODE)
                logger.info(
                    f"Access Point started: {self.settings.ap_ssid} with password: {ap_password}"
                )

                # Enable captive portal for automatic browser popup
                if self.settings.enable_captive_portal:
                    logger.info("Enabling captive portal...")
                    captive_enabled = await self.web_server.enable_captive_portal()
                    if captive_enabled:
                        logger.info("Captive portal enabled - devices will auto-open browser")
                    else:
                        logger.warning(
                            "Failed to enable captive portal - manual browser navigation required"
                        )
            else:
                logger.error("Failed to start Access Point mode")
                raise RuntimeError("Cannot start without AP mode")
        # Start Avahi service advertisement
        self.avahi_service.start()
        logger.info(f"Avahi service started on port {self.settings.web_port}")

        self.state_manager.on_state_change(self._handle_state_change)

        logger.info("Initialization complete")

    async def _handle_state_change(self, old_state: ConnectionState, new_state: ConnectionState):
        logger.info(f"State transition: {old_state} -> {new_state}")

        # Disable captive portal when leaving AP mode
        if old_state == ConnectionState.AP_MODE and new_state != ConnectionState.AP_MODE:
            if self.settings.enable_captive_portal:
                logger.info("Disabling captive portal as we're leaving AP mode")
                await self.web_server.disable_captive_portal()

        # Avahi handles all network transitions automatically
        # No need to manage mDNS state changes

    async def run_web_server(self):
        uvicorn_logger = logging.getLogger("uvicorn.error")
        if not self.settings.debug:
            uvicorn_logger.setLevel(logging.ERROR)

        config = uvicorn.Config(
            app=self.web_server.get_app(),
            host=self.settings.web_host,
            port=self.settings.web_port,
            log_level="info" if self.settings.debug else "error",
            access_log=self.settings.debug,
        )
        self.server = uvicorn.Server(config)
        await self.server.serve()

    async def run_session_cleanup(self):
        while self.running:
            try:
                await self.state_manager.remove_stale_sessions(max_age_seconds=3600)
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
                await asyncio.sleep(60)

    async def run_network_monitor(self):
        await self.network_manager.monitor_events()

    async def run(self):
        self.running = True

        try:
            await self.initialize()
            self.tasks = [
                asyncio.create_task(self.run_web_server()),
                asyncio.create_task(self.display_service.run()),
                asyncio.create_task(self.tunnel_service.run()),
                asyncio.create_task(self.run_session_cleanup()),
            ]

            self.tasks.append(asyncio.create_task(self.run_network_monitor()))

            logger.info("All services started successfully")

            # Get the actual hostname (what Avahi is using)
            actual_hostname = socket.gethostname()

            # Display accessible URLs based on connection state
            state = self.state_manager.get_state()
            if (
                state.connection_state == ConnectionState.CONNECTED
                and state.network_info.ip_address
            ):
                logger.info("=" * 60)
                logger.info("Web interface accessible at:")
                logger.info(f"  - http://{state.network_info.ip_address}:{self.settings.web_port}")
                logger.info(f"  - http://{actual_hostname}.local:{self.settings.web_port}")
                logger.info("=" * 60)
            elif state.connection_state == ConnectionState.AP_MODE:
                logger.info("=" * 60)
                logger.info("Web interface accessible at:")
                logger.info(f"  - http://{self.settings.ap_ip}:{self.settings.web_port}")
                logger.info(f"  - http://{actual_hostname}.local:{self.settings.web_port}")
                logger.info("=" * 60)
            else:
                logger.info(
                    f"Web interface available at: http://{actual_hostname}.local:{self.settings.web_port}"
                )

            await asyncio.gather(*self.tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self):
        logger.info("Shutting down services...")
        self.running = False

        if self.server:
            self.server.should_exit = True
        for task in self.tasks:
            if not task.done():
                task.cancel()

        if self.tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.tasks, return_exceptions=True), timeout=5.0
                )
            except TimeoutError:
                logger.warning("Some tasks did not complete within timeout")

        try:
            # Disable captive portal if it was enabled
            if self.settings.enable_captive_portal:
                await self.web_server.disable_captive_portal()

            self.avahi_service.stop()
            await self.display_service.stop()
            await self.tunnel_service.stop()
        except Exception as e:
            logger.error(f"Error stopping services: {e}")

        if self.state_manager.is_connected():
            try:
                await self.network_manager.disconnect_from_network()
            except Exception as e:
                logger.error(f"Error disconnecting from network: {e}")

        logger.info("Shutdown complete")


def main():
    if os.geteuid() != 0:
        print("Error: This application requires root privileges.")
        print("Please run with sudo:")
        print(f"  sudo {' '.join(sys.argv)}")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Distiller WiFi Provisioning System")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")

    args = parser.parse_args()

    state_dir = Path("/var/lib/distiller")
    log_dir = Path("/var/log/distiller")

    for directory in [state_dir, log_dir]:
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o755)

    settings = get_settings()
    if args.debug:
        settings.debug = True
        setup_logging(debug=True)

    if args.port:
        settings.web_port = args.port
        settings.mdns_port = args.port

    app = DistillerWiFiApp(settings)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
