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
        hostname: str = "pamir-ai",
        service_name: str = "Pamir AI Device",
        port: int = 8080,
    ):
        self.hostname = hostname
        self.service_name = service_name
        self.port = port
        self.zeroconf: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.app = FastAPI(title="Pamir AI Device")
        self.server: Optional[uvicorn.Server] = None

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Setup web routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.get("/", response_class=HTMLResponse)
        async def home(request: Request):
            """Main page showing Cursor MCP message"""
            html_content = (
                """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Pamir AI Device - Ready</title>
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    body {
                        font-family: 'Courier New', 'Monaco', 'Menlo', monospace;
                        background: #fafafa;
                        color: #1a1a1a;
                        min-height: 100vh;
                        padding: 24px;
                        line-height: 1.6;
                    }

                    .container {
                        max-width: 640px;
                        margin: 0 auto;
                        background: #ffffff;
                        border: 2px solid #1a1a1a;
                        box-shadow: 8px 8px 0px #1a1a1a;
                    }

                    .header {
                        background: #1a1a1a;
                        color: #ffffff;
                        padding: 24px;
                        border-bottom: 2px solid #1a1a1a;
                        text-align: center;
                    }

                    .header h1 {
                        font-size: 1.75rem;
                        font-weight: bold;
                        letter-spacing: -0.02em;
                        margin-bottom: 8px;
                        text-transform: uppercase;
                    }

                    .header p {
                        font-size: 0.95rem;
                        opacity: 0.8;
                    }

                    .content {
                        padding: 32px;
                    }

                    .status-card {
                        background: #f8f8f8;
                        border: 2px solid #1a1a1a;
                        padding: 20px;
                        margin-bottom: 24px;
                        position: relative;
                        text-align: center;
                    }

                    .status-card::before {
                        content: '';
                        position: absolute;
                        top: -2px;
                        left: -2px;
                        right: -2px;
                        height: 4px;
                        background: #28a745;
                    }

                    .status-title {
                        font-weight: bold;
                        color: #1a1a1a;
                        margin-bottom: 12px;
                        text-transform: uppercase;
                        font-size: 0.85rem;
                        letter-spacing: 0.05em;
                    }

                    .status-info {
                        color: #4a4a4a;
                        font-size: 0.9rem;
                    }

                    .info-section {
                        margin-bottom: 24px;
                        text-align: center;
                    }

                    .main-message {
                        font-size: 1.1rem;
                        margin-bottom: 16px;
                        padding: 16px;
                        background: #f8f8f8;
                        border: 2px solid #1a1a1a;
                        font-weight: bold;
                        text-transform: uppercase;
                        letter-spacing: 0.02em;
                    }

                    .highlight {
                        background: #1a1a1a;
                        color: #ffffff;
                        padding: 2px 8px;
                        font-weight: bold;
                    }

                    .instructions {
                        background: #f8f8f8;
                        border: 2px solid #1a1a1a;
                        padding: 20px;
                        margin-bottom: 24px;
                        position: relative;
                    }

                    .instructions::before {
                        content: '';
                        position: absolute;
                        top: -2px;
                        left: -2px;
                        right: -2px;
                        height: 4px;
                        background: #1a1a1a;
                    }

                    .instructions h3 {
                        font-weight: bold;
                        color: #1a1a1a;
                        margin-bottom: 12px;
                        text-transform: uppercase;
                        font-size: 0.9rem;
                        letter-spacing: 0.05em;
                    }

                    .network-info {
                        background: #1a1a1a;
                        color: #ffffff;
                        padding: 20px;
                        border: 2px solid #1a1a1a;
                        margin-bottom: 24px;
                        font-size: 0.9rem;
                    }

                    .network-info div {
                        margin-bottom: 8px;
                    }

                    .network-info strong {
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                        font-size: 0.8rem;
                    }

                    .footer {
                        text-align: center;
                        color: #4a4a4a;
                        font-size: 0.8rem;
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                        padding-top: 16px;
                        border-top: 2px solid #f8f8f8;
                    }

                    .icon {
                        font-size: 2rem;
                        margin-bottom: 16px;
                        display: block;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Device Ready</h1>
                        <p>Connection Established Successfully</p>
                    </div>
                    
                    <div class="content">
                        <div class="status-card">
                            <div class="status-title">Connection Status</div>
                            <div class="status-info">WiFi Connected Successfully</div>
                        </div>
                        
                        <div class="info-section">
                            <div class="main-message">
                                <span class="highlight">Now you can use Cursor to play with MCP!</span>
                            </div>
                            <p style="color: #4a4a4a; font-size: 0.9rem;">
                                Your device is connected to the network and ready for development.
                            </p>
                        </div>
                        
                        <div class="instructions">
                            <h3>What's Next?</h3>
                            <p style="color: #4a4a4a; font-size: 0.9rem;">
                                Open <strong>Cursor IDE</strong> and start experimenting with 
                                <strong>Model Context Protocol (MCP)</strong> integrations.
                                Your Pamir AI device is now accessible on the local network.
                            </p>
                        </div>
                        
                        <div class="network-info">
                            <div><strong>Device:</strong> """
                + self.hostname
                + """.local</div>
                            <div><strong>Service:</strong> """
                + self.service_name
                + """</div>
                            <div><strong>Port:</strong> """
                + str(self.port)
                + """</div>
                        </div>
                        
                        <div class="footer">
                            <p>Pamir AI • mDNS Service Active</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            )
            return HTMLResponse(content=html_content)

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
            html_content = (
                """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>WiFi Status - Pamir AI Device</title>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body { 
                        font-family: 'Courier New', 'Monaco', 'Menlo', monospace;
                        background: #fafafa; color: #1a1a1a; min-height: 100vh; padding: 24px; line-height: 1.6;
                    }
                    .container { 
                        max-width: 640px; margin: 0 auto; background: #ffffff;
                        border: 2px solid #1a1a1a; box-shadow: 8px 8px 0px #1a1a1a;
                    }
                    .header { 
                        background: #1a1a1a; color: #ffffff; padding: 24px; text-align: center;
                    }
                    .header h1 { font-size: 1.75rem; margin-bottom: 8px; text-transform: uppercase; }
                    .content { padding: 32px; }
                    .status-card { 
                        background: #f8f8f8; border: 2px solid #1a1a1a; padding: 20px; 
                        margin-bottom: 24px; text-align: center;
                    }
                    .status-card.success::before {
                        content: ''; position: absolute; top: -2px; left: -2px; right: -2px;
                        height: 4px; background: #28a745;
                    }
                    .status-title { 
                        font-weight: bold; margin-bottom: 12px; text-transform: uppercase;
                        font-size: 0.85rem; letter-spacing: 0.05em;
                    }
                    .btn { 
                        background: #1a1a1a; color: #ffffff; border: none; padding: 12px 24px;
                        font-family: inherit; cursor: pointer; text-decoration: none;
                        display: inline-block; margin: 5px; text-transform: uppercase;
                        font-size: 0.9rem; letter-spacing: 0.05em;
                    }
                    .btn:hover { background: #333; }
                    .btn-secondary { background: #666; }
                    .alert { 
                        padding: 16px; margin: 16px 0; border: 2px solid #1a1a1a;
                        background: #e7f3ff; text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>WiFi Connection Status</h1>
                        <p>Pamir AI Device Network Information</p>
                    </div>
                    
                    <div class="content">
                        <div class="status-card success" style="position: relative;">
                            <div class="status-title">✅ WiFi Connection Successful</div>
                            <div class="status-info">
                                Your device is now connected to the WiFi network and accessible via mDNS.
                            </div>
                        </div>
                        
                        <div class="alert">
                            <strong>Note:</strong> The WiFi setup server runs on port 8080 for 2 minutes after connection, 
                            then switches to this permanent service on port """
                + str(self.port)
                + """.
                        </div>
                        
                        <div style="text-align: center; margin-top: 24px;">
                            <p style="margin-bottom: 16px;">Try accessing the setup server while it's still active:</p>
                            <a href="http://"""
                + self.hostname
                + """.local:8080/wifi_status" class="btn">
                                Check Setup Server (Port 8080)
                            </a>
                            <a href="/" class="btn btn-secondary">
                                Return to Device Home
                            </a>
                        </div>
                        
                        <div style="margin-top: 32px; padding: 20px; background: #f8f8f8; border: 2px solid #1a1a1a;">
                            <h3 style="margin-bottom: 12px; text-transform: uppercase; font-size: 0.9rem;">Device Access Information:</h3>
                            <div style="font-size: 0.9rem;">
                                <div><strong>Hostname:</strong> """
                + self.hostname
                + """.local</div>
                                <div><strong>Setup Server:</strong> Port 8080 (temporary, 2 minutes)</div>
                                <div><strong>Device Service:</strong> Port """
                + str(self.port)
                + """ (permanent)</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <script>
                    // Auto-refresh every 10 seconds to update status
                    setTimeout(() => window.location.reload(), 10000);
                </script>
            </body>
            </html>
            """
            )
            return HTMLResponse(content=html_content)

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
                    "device": "pamir-ai",
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

    parser = argparse.ArgumentParser(description="mDNS Service for Pamir AI Device")
    parser.add_argument(
        "--hostname", default="pamir-ai", help="Hostname for mDNS (default: pamir-ai)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for web server (default: 8080)"
    )
    parser.add_argument(
        "--service-name", default="Pamir AI Device", help="Service name"
    )
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
