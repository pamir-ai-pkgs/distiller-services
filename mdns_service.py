#!/usr/bin/env python3
"""
mDNS Service - Advertise device on local network after WiFi connection

Provides a simple web interface accessible via hostname.local
"""

import asyncio
import logging
import socket
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf


class MDNSService:
    """mDNS service for advertising the device on local network"""

    def __init__(
        self,
        hostname: str = "",
        service_name: str = "Distiller",
        port: int = 8080,
    ):
        self.hostname = hostname
        self.service_name = service_name
        self.port = port
        self.zeroconf: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.app = FastAPI(title="Distiller")
        self.server: Optional[uvicorn.Server] = None
        self.templates = Jinja2Templates(directory="templates")

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Setup web routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.get("/", response_class=HTMLResponse)
        async def home(request: Request):
            """Main page showing Cursor MCP message"""
            return self.templates.TemplateResponse(
                "mdns_home.html",
                {
                    "request": request,
                    "hostname": self.hostname,
                    "service_name": self.service_name,
                    "port": self.port,
                },
            )

        @self.app.get("/api/status")
        async def status():
            """API endpoint for device status"""
            return {
                "status": "connected",
                "hostname": f"{self.hostname}.local",
                "service": self.service_name,
                "port": self.port,
                "mdns_active": self.zeroconf is not None,
            }

        @self.app.get("/wifi_status", response_class=HTMLResponse)
        async def wifi_status(request: Request):
            """WiFi status page with helpful information"""
            return self.templates.TemplateResponse(
                "mdns_wifi_status.html",
                {
                    "request": request,
                    "hostname": self.hostname,
                    "port": self.port,
                },
            )

    def get_local_ip(self) -> str:
        """Get the local IP address"""
        try:
            # Connect to a remote address to get local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    async def start_mdns(self):
        """Start mDNS service advertising"""
        if self.zeroconf is not None:
            self.logger.warning("mDNS service already running")
            return

        try:
            self.zeroconf = AsyncZeroconf()

            # Get local IP
            local_ip = self.get_local_ip()
            self.logger.info(f"Advertising mDNS service on {local_ip}:{self.port}")

            # Create service info
            self.service_info = ServiceInfo(
                "_http._tcp.local.",
                f"{self.hostname}._http._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "description": self.service_name,
                    "path": "/",
                    "version": "1.0",
                    "device": "distiller",
                },
                server=f"{self.hostname}.local.",
            )

            # Register service
            await self.zeroconf.async_register_service(self.service_info)
            self.logger.info(
                f"mDNS service registered: {self.hostname}.local:{self.port}"
            )

        except Exception as e:
            self.logger.error(f"Failed to start mDNS service: {e}")
            if self.zeroconf:
                await self.zeroconf.async_close()
                self.zeroconf = None

    async def stop_mdns(self):
        """Stop mDNS service"""
        if self.zeroconf:
            try:
                if self.service_info:
                    await self.zeroconf.async_unregister_service(self.service_info)
                await self.zeroconf.async_close()
                self.logger.info("mDNS service stopped")
            except Exception as e:
                self.logger.error(f"Error stopping mDNS service: {e}")
            finally:
                self.zeroconf = None
                self.service_info = None

    async def start_web_server(self):
        """Start the web server"""
        try:
            config = uvicorn.Config(
                self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning",
                access_log=False,
            )

            self.server = uvicorn.Server(config)
            self.logger.info(f"Starting mDNS web server on port {self.port}")

            # Start mDNS advertising
            await self.start_mdns()

            # Run server in background task
            server_task = asyncio.create_task(self.server.serve())
            return server_task

        except OSError as e:
            if e.errno == 98:  # Address already in use
                self.logger.error(
                    f"Port {self.port} is already in use. Please choose a different port or stop the conflicting service."
                )
                # Try alternative ports
                for alt_port in [self.port + 1, self.port + 2, 8001, 8002, 8003]:
                    try:
                        self.logger.info(f"Trying alternative port {alt_port}...")
                        self.port = alt_port
                        config = uvicorn.Config(
                            self.app,
                            host="0.0.0.0",
                            port=self.port,
                            log_level="warning",
                            access_log=False,
                        )
                        self.server = uvicorn.Server(config)
                        await self.start_mdns()
                        server_task = asyncio.create_task(self.server.serve())
                        self.logger.info(
                            f"Successfully started mDNS web server on alternative port {self.port}"
                        )
                        return server_task
                    except OSError:
                        continue
                raise Exception(
                    f"Could not find an available port starting from {self.port}"
                )
            else:
                raise
        except Exception as e:
            self.logger.error(f"Failed to start mDNS web server: {e}")
            raise

    async def stop_web_server(self):
        """Stop the web server"""
        if self.server:
            self.logger.info("Stopping mDNS web server...")
            self.server.should_exit = True
            await asyncio.sleep(1)  # Give server time to stop

        await self.stop_mdns()

    async def run(self):
        """Run the mDNS service (for standalone use)"""
        try:
            self.logger.info(f"Starting mDNS service: {self.hostname}.local")
            server_task = await self.start_web_server()

            print(f"\nmDNS Service Started")
            print(f"Access your device at:")
            print(f"   * http://{self.hostname}.local:{self.port}")
            print(f"   * http://{self.get_local_ip()}:{self.port}")
            print(f"\nNow you can use Cursor to play with MCP!")
            print(f"Note: If .local doesn't work, use the direct IP address")
            print("Press Ctrl+C to stop\n")

            # Wait for server
            await server_task

        except KeyboardInterrupt:
            self.logger.info("mDNS service interrupted by user")
        except Exception as e:
            self.logger.error(f"mDNS service error: {e}")
        finally:
            await self.stop_web_server()


async def main():
    """Main entry point for standalone use"""
    import argparse

    parser = argparse.ArgumentParser(description="mDNS Service for Distiller")
    parser.add_argument(
        "--hostname", default="", help="Hostname for mDNS"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for web server (default: 8080)"
    )
    parser.add_argument("--service-name", default="Distiller", help="Service name")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create and run service
    mdns_service = MDNSService(args.hostname, args.service_name, args.port)
    await mdns_service.run()


if __name__ == "__main__":
    asyncio.run(main())
