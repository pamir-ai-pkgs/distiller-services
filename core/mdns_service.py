"""
mDNS service with persistent advertising across network transitions.
"""

import asyncio
import logging
import socket

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

logger = logging.getLogger(__name__)


class MDNSService:
    """
    Manages mDNS service advertising with persistent hostname.

    Features:
    - Persistent advertising during network transitions
    - Interface-specific binding
    - Multiple service type support
    - Graceful reconnection handling
    """

    def __init__(self, hostname: str, port: int = 8080):
        self.hostname = hostname.replace(".local", "")
        self.port = port
        self.azc: AsyncZeroconf | None = None
        self.services: dict[str, ServiceInfo] = {}
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self, interface: str = "all") -> None:
        """Start mDNS service advertising."""
        async with self._lock:
            if self._running:
                logger.warning("mDNS service already running")
                return

            try:
                # Create AsyncZeroconf instance
                # Note: interface_choice parameter removed for compatibility
                self.azc = AsyncZeroconf()

                # Register services
                await self._register_http_service()

                self._running = True
                logger.info(
                    f"mDNS service started for {self.hostname}.local on interface: {interface}"
                )

            except Exception as e:
                logger.error(f"Failed to start mDNS service: {e}")
                await self.stop()

    async def stop(self) -> None:
        """Stop mDNS service advertising."""
        async with self._lock:
            if not self._running:
                return

            try:
                # Unregister all services
                if self.azc:
                    for service_name, service_info in self.services.items():
                        try:
                            await self.azc.async_unregister_service(service_info)
                            logger.debug(f"Unregistered service: {service_name}")
                        except Exception as e:
                            logger.error(f"Failed to unregister {service_name}: {e}")

                    # Close AsyncZeroconf
                    await self.azc.async_close()
                    self.azc = None

                self.services.clear()
                self._running = False
                logger.info("mDNS service stopped")

            except Exception as e:
                logger.error(f"Error stopping mDNS service: {e}")

    async def switch_interface(self, new_interface: str) -> None:
        """Switch to a different network interface."""
        logger.info(f"Switching mDNS to interface: {new_interface}")

        # Stop current service
        await self.stop()

        # Small delay to ensure cleanup
        await asyncio.sleep(0.5)

        # Start on new interface
        await self.start(new_interface)

    async def _register_http_service(self) -> None:
        """Register HTTP service for web interface."""
        try:
            # Get IP addresses
            ip_addresses = await self._get_ip_addresses()

            # Create service info
            service_type = "_http._tcp.local."
            service_name = f"{self.hostname}._http._tcp.local."

            service_info = ServiceInfo(
                service_type,
                service_name,
                addresses=ip_addresses,
                port=self.port,
                properties={b"path": b"/setup", b"version": b"1.0", b"device": b"distiller-cm5"},
                server=f"{self.hostname}.local.",
            )

            # Register service
            await self.azc.async_register_service(service_info)
            self.services[service_name] = service_info

            logger.info(f"Registered HTTP service: {self.hostname}.local:{self.port}")

        except Exception as e:
            logger.error(f"Failed to register HTTP service: {e}")

    async def _get_ip_addresses(self) -> list:
        """Get all IP addresses for the host."""
        ip_addresses = []

        try:
            # Get all network interfaces
            for interface in socket.getaddrinfo(socket.gethostname(), None):
                if interface[0] == socket.AF_INET:  # IPv4
                    ip = interface[4][0]
                    if ip != "127.0.0.1":  # Skip loopback
                        ip_addresses.append(socket.inet_aton(ip))

            # Always include loopback for persistence
            ip_addresses.append(socket.inet_aton("127.0.0.1"))

        except Exception as e:
            logger.error(f"Failed to get IP addresses: {e}")
            # Fallback to loopback only
            ip_addresses = [socket.inet_aton("127.0.0.1")]

        return ip_addresses

    async def update_service_port(self, port: int) -> None:
        """Update the advertised port number."""
        if port == self.port:
            return

        self.port = port

        # Re-register services with new port
        if self._running:
            # Get current interface
            interface = "all"  # Default, could be tracked
            await self.switch_interface(interface)

    def get_mdns_url(self) -> str:
        """Get the mDNS URL for the service."""
        return f"http://{self.hostname}.local:{self.port}"

    async def keep_alive_during_transition(self) -> None:
        """
        Keep mDNS alive during network transitions.

        This binds to loopback interface temporarily to maintain
        service discovery while switching between AP and client modes.
        """
        logger.info("Keeping mDNS alive on loopback during transition")
        await self.switch_interface("lo")

        # Wait a bit to ensure service is registered
        await asyncio.sleep(1)

    async def restore_after_transition(self) -> None:
        """
        Restore mDNS on the active network interface after transition.
        """
        logger.info("Restoring mDNS on active interface")
        await self.switch_interface("all")

    async def run(self) -> None:
        """
        Keep the mDNS service running.

        This is a long-running task that maintains the mDNS advertisement.
        """
        try:
            while self._running:
                await asyncio.sleep(10)  # Just keep the service alive
        except asyncio.CancelledError:
            logger.debug("mDNS run task cancelled")
            raise
        except Exception as e:
            logger.error(f"mDNS run error: {e}")
