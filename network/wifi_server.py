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
            }
        except Exception as e:
            self.logger.error(f"Status check failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get status")

    async def connect_network(self, request: ConnectRequest) -> Dict:
        """POST /api/connect - Connect to WiFi network"""
        try:
            self.logger.info(f"Connection request for SSID: {request.ssid}")

            # If hotspot is active, first check network existence
            if self.wifi_manager._hotspot_active:
                # Quick network existence check without hotspot disruption
                if not await self.wifi_manager._network_exists(request.ssid):
                    return {
                        "success": False,
                        "redirect_to_status": False,
                        "message": f"Network '{request.ssid}' not found. Please check the network name and ensure it's available."
                    }
                
                # Network exists - we'll need to stop hotspot, so signal redirect
                self.logger.info(f"Network {request.ssid} found, starting connection process")
                
                # Mark connection as in progress
                import time
                self._connection_in_progress = True
                self._connection_start_time = time.time()
                
                # Start the connection process in background with a delay
                # This gives time for the response to reach frontend and redirect to happen
                asyncio.create_task(self._perform_connection_with_delay(request.ssid, request.password))
                
                return {
                    "success": False,  # Not connected yet
                    "redirect_to_status": True,  # Signal frontend to redirect
                    "message": f"Connection to {request.ssid} initiated. Check status page for results."
                }
            else:
                # No hotspot - can handle normally with retries
                success = await self.wifi_manager.connect_to_network(
                    request.ssid, request.password, max_retries=3
                )

                if success:
                    await asyncio.sleep(2)
                    status = await self.wifi_manager.get_connection_status()
                    return {
                        "success": True,
                        "message": f"Successfully connected to {request.ssid}",
                        "status": {
                            "connected": status.connected,
                            "ssid": status.ssid,
                            "ip_address": status.ip_address,
                        },
                    }
                else:
                    return {
                        "success": False,
                        "redirect_to_status": False,
                        "message": f"Failed to connect to {request.ssid} after multiple attempts."
                    }

        except WiFiManagerError as e:
            self.logger.error(f"Connection failed: {e}")
            error_detail = str(e)

            # These are immediate errors (network not found, etc.) - no hotspot disruption
            raise HTTPException(status_code=400, detail=error_detail)
        except Exception as e:
            self.logger.error(f"Unexpected connection error: {e}")
            raise HTTPException(
                status_code=500, detail="Connection failed due to unexpected error"
            )

    async def _perform_connection_with_delay(self, ssid: str, password: str):
        """Perform connection with hotspot management in background with delay"""
        try:
            # Wait for frontend to receive response and redirect (5 seconds should be enough)
            self.logger.info(f"Waiting 5 seconds before starting connection to {ssid} to allow frontend redirect")
            await asyncio.sleep(5)
            
            self.logger.info(f"Starting actual connection to {ssid}")
            success = await self.wifi_manager.connect_to_network(ssid, password, max_retries=3)
            
            if success:
                self.logger.info(f"Background connection to {ssid} completed successfully")
            else:
                self.logger.error(f"Background connection to {ssid} failed")
            
            # Clear connection progress flags
            self._connection_in_progress = False
            self._connection_start_time = None
            
        except Exception as e:
            self.logger.error(f"Background connection to {ssid} failed: {e}")
            
            # Clear connection progress flags on failure
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
