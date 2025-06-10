"""
FastAPI Web Server for WiFi Setup Interface

Provides REST API endpoints and web interface for WiFi configuration.
"""

import asyncio
import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request
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
        self, wifi_manager: WiFiManager, host: str = "0.0.0.0", port: int = 8080
    ):
        self.wifi_manager = wifi_manager
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.templates = Jinja2Templates(directory="templates")
        self.app = self._create_app()
        self._setup_complete = False

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

        return app

    async def get_status(self) -> Dict:
        """GET /api/status - Get connection status"""
        try:
            status = await self.wifi_manager.get_connection_status()
            return {
                "connected": status.connected,
                "ssid": status.ssid,
                "interface": status.interface,
                "ip_address": status.ip_address,
                "setup_complete": self._setup_complete,
            }
        except Exception as e:
            self.logger.error(f"Status check failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get status")

    async def connect_network(self, request: ConnectRequest) -> Dict:
        """POST /api/connect - Connect to WiFi network"""
        try:
            self.logger.info(f"Connection request for SSID: {request.ssid}")

            # Check if hotspot is active to inform user about the process
            if self.wifi_manager._hotspot_active:
                self.logger.info("Stopping hotspot for connection attempt")

            success = await self.wifi_manager.connect_to_network(
                request.ssid, request.password
            )

            if success:
                # Give network time to fully establish
                await asyncio.sleep(2)
                status = await self.wifi_manager.get_connection_status()

                return {
                    "success": True,
                    "message": f"Successfully connected to {request.ssid}",
                    "hotspot_stopped": True,  # Indicate hotspot was stopped
                    "status": {
                        "connected": status.connected,
                        "ssid": status.ssid,
                        "ip_address": status.ip_address,
                    },
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to connect to {request.ssid}. Hotspot has been restored.",
                    "hotspot_restored": True,
                }

        except WiFiManagerError as e:
            self.logger.error(f"Connection failed: {e}")
            # Extract more user-friendly error messages
            error_detail = str(e)
            if "No network with SSID" in error_detail:
                error_detail = f"Network '{request.ssid}' not found. Make sure the network name is correct and the network is available."
            elif "Connection failed" in error_detail:
                error_detail = f"Failed to connect to '{request.ssid}'. Please check the password and try again."

            raise HTTPException(status_code=400, detail=error_detail)
        except Exception as e:
            self.logger.error(f"Unexpected connection error: {e}")
            raise HTTPException(
                status_code=500, detail="Connection failed due to unexpected error"
            )

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

    def is_setup_complete(self) -> bool:
        """Check if setup has been marked as complete"""
        return self._setup_complete
