"""
FastAPI Web Server for WiFi Setup Interface

Provides REST API endpoints and web interface for WiFi configuration.
"""

import asyncio
import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .wifi_manager import WiFiManager, WiFiManagerError


class ConnectRequest(BaseModel):
    """WiFi connection request model"""

    ssid: str
    password: str = ""  # Optional password field


class HotspotRequest(BaseModel):
    """Hotspot configuration request model"""

    ssid: str = "SetupWiFi"
    password: str = "setupwifi123"


class ForgetRequest(BaseModel):
    """Network forget request model"""

    ssid: str


class WiFiServer:
    """FastAPI-based WiFi setup web server"""

    def __init__(
        self, wifi_manager: WiFiManager, host: str = "0.0.0.0", port: int = 8080, mdns_hostname: str = None
    ):
        self.wifi_manager = wifi_manager
        self.host = host
        self.port = port
        self.mdns_hostname = mdns_hostname
        self.logger = logging.getLogger(__name__)
        self.templates = Jinja2Templates(directory="templates")
        self.app = self._create_app()
        self._setup_complete = False
        self._connection_in_progress = False
        self._connection_start_time = None

    def _create_app(self) -> FastAPI:
        """Create and configure FastAPI application"""
        app = FastAPI(
            title="WiFi Setup Service",
            description="Web interface for WiFi network configuration",
            version="1.0.0",
        )

        # Mount static files
        app.mount("/static", StaticFiles(directory="static"), name="static")

        # API Routes
        app.get("/api/status")(self.get_status)
        app.post("/api/connect")(self.connect_network)
        app.post("/api/forget")(self.forget_network)
        app.post("/api/hotspot/start")(self.start_hotspot)
        app.post("/api/hotspot/stop")(self.stop_hotspot)
        app.post("/api/complete-setup")(self.complete_setup)

        # Web Interface
        app.get("/", response_class=HTMLResponse)(self.get_index)
        app.get("/wifi_status", response_class=HTMLResponse)(self.get_wifi_status)

        return app

    async def get_status(self) -> Dict:
        """GET /api/status - Get connection status"""
        try:
            status = await self.wifi_manager.get_connection_status()
            
            # Check if connection is in progress
            connection_in_progress = False
            if self._connection_in_progress and self._connection_start_time:
                # Consider connection in progress for up to 2 minutes
                import time
                elapsed = time.time() - self._connection_start_time
                connection_in_progress = elapsed < 120  # 2 minutes timeout
                
                if not connection_in_progress:
                    # Reset if timeout exceeded
                    self._connection_in_progress = False
                    self._connection_start_time = None
            
            return {
                "connected": status.connected,
                "ssid": status.ssid,
                "interface": status.interface,
                "ip_address": status.ip_address,
                "setup_complete": self._setup_complete,
                "connection_in_progress": connection_in_progress,
                "mdns_hostname": self.mdns_hostname,
            }
        except Exception as e:
            self.logger.error(f"Status check failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get status")

    async def connect_network(self, request: ConnectRequest, background_tasks: BackgroundTasks) -> Dict:
        """POST /api/connect - Immediately responds and triggers connection in the background."""
        try:
            self.logger.info(f"Connection request for SSID: {request.ssid}")

            # This is the key change: schedule the connection to run in the background
            # after this function returns a response.
            background_tasks.add_task(
                self._perform_connection_with_delay, request.ssid, request.password
            )

            # Set flags to indicate a connection is starting
            self._connection_in_progress = True
            import time
            self._connection_start_time = time.time()

            # Immediately return a response to the client
            # This tells the frontend that the process has started and it should redirect.
            return {
                "success": True,
                "message": "Connection process initiated. Redirecting to check status...",
                "redirect_to_status": True,
            }

        except Exception as e:
            self.logger.error(f"Unexpected error initiating connection: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to start connection process"
            )

    async def _perform_connection_with_delay(self, ssid: str, password: str):
        """Perform connection with hotspot management in background."""
        try:
            # A short delay can sometimes help ensure the HTTP response is sent before
            # the network interface is disrupted.
            await asyncio.sleep(2)
            
            self.logger.info(f"Background task: Starting actual connection to {ssid}")
            
            # This now runs independently of the user's browser session
            await self.wifi_manager.connect_to_network(ssid, password, max_retries=3)
            
            # Note: We don't set the in-progress flags to False here.
            # They will time out naturally in the get_status endpoint,
            # which correctly reflects the "connecting" state for a period.
            
        except Exception as e:
            self.logger.error(f"Background connection to {ssid} failed: {e}")
            # If the connection fails, the flags will eventually time out,
            # and the status page will reflect the failure.
            self._connection_in_progress = False
            self._connection_start_time = None

    async def forget_network(self, request: ForgetRequest) -> Dict:
        """POST /api/forget - Forget saved network"""
        try:
            success = await self.wifi_manager.forget_network(request.ssid)
            return {
                "success": success,
                "message": f"Network {request.ssid} {'forgotten' if success else 'not found'}",
            }
        except Exception as e:
            self.logger.error(f"Forget network failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to forget network")

    async def start_hotspot(self, request: HotspotRequest) -> Dict:
        """POST /api/hotspot/start - Start WiFi hotspot"""
        try:
            success = await self.wifi_manager.start_hotspot(
                request.ssid, request.password
            )
            return {
                "success": success,
                "message": f"Hotspot {'started' if success else 'failed to start'}",
                "ssid": request.ssid,
            }
        except WiFiManagerError as e:
            self.logger.error(f"Hotspot start failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def stop_hotspot(self) -> Dict:
        """POST /api/hotspot/stop - Stop WiFi hotspot"""
        try:
            success = await self.wifi_manager.stop_hotspot()
            return {
                "success": success,
                "message": f"Hotspot {'stopped' if success else 'failed to stop'}",
            }
        except Exception as e:
            self.logger.error(f"Hotspot stop failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to stop hotspot")

    async def complete_setup(self) -> Dict:
        """POST /api/complete-setup - Signal setup completion"""
        self._setup_complete = True
        self.logger.info("Setup marked as complete")
        return {"success": True, "message": "Setup completed successfully"}

    async def get_index(self, request: Request) -> HTMLResponse:
        """GET / - Main web interface"""
        return self.templates.TemplateResponse("index.html", {"request": request})

    async def get_wifi_status(self, request: Request) -> HTMLResponse:
        """GET /wifi_status - WiFi connection status page"""
        try:
            status = await self.wifi_manager.get_connection_status()
            
            # Check if connection is in progress
            connection_in_progress = False
            if self._connection_in_progress and self._connection_start_time:
                import time
                elapsed = time.time() - self._connection_start_time
                connection_in_progress = elapsed < 120  # 2 minutes timeout
            
            # Check if we're connected to a real WiFi network (not our hotspot)
            if status.connected and status.ssid and not status.ssid.startswith("SetupWiFi"):
                # Successfully connected to a WiFi network
                return self.templates.TemplateResponse("wifi_status.html", {
                    "request": request,
                    "success": True,
                    "connection_in_progress": False,
                    "status": {
                        "ssid": status.ssid,
                        "ip_address": status.ip_address,
                        "interface": status.interface
                    }
                })
            elif connection_in_progress:
                # Connection attempt is in progress
                return self.templates.TemplateResponse("wifi_status.html", {
                    "request": request,
                    "success": False,
                    "connection_in_progress": True,
                    "message": "Connection attempt in progress... Please wait."
                })
            else:
                # Connection failed or back on hotspot
                return self.templates.TemplateResponse("wifi_status.html", {
                    "request": request,
                    "success": False,
                    "connection_in_progress": False,
                    "message": "Connection failed. Please try again."
                })
                
        except Exception as e:
            self.logger.error(f"WiFi status check failed: {e}")
            return self.templates.TemplateResponse("wifi_status.html", {
                "request": request,
                "success": False,
                "connection_in_progress": False,
                "message": "Unable to check connection status. Please try again."
            })

    def is_setup_complete(self) -> bool:
        """Check if setup has been marked as complete"""
        return self._setup_complete
