"""FastAPI web server with WebSocket support."""

import asyncio
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from core.captive_portal import CaptivePortal
from core.config import Settings, generate_secure_password
from core.network_manager import NetworkManager
from core.state import ConnectionState, NetworkInfo, SessionInfo, StateManager

logger = logging.getLogger(__name__)


class ConnectionRequest(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=32)
    password: str | None = Field(None, min_length=8, max_length=63)

    @field_validator("ssid")
    @classmethod
    def validate_ssid(cls, v):
        # Check for dangerous characters that could be used in command injection
        if not v or len(v.strip()) == 0:
            raise ValueError("SSID cannot be empty")
        # Allow only safe characters for SSID
        if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", v):
            raise ValueError("SSID contains invalid characters")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if v is None:
            return None
        # WPA/WPA2 requires 8-63 characters
        if len(v) < 8 or len(v) > 63:
            raise ValueError("Password must be 8-63 characters")
        # Check for shell-dangerous characters
        dangerous_chars = ["`", "$", "\\", '"', "'", ";", "&", "|", ">", "<", "\n", "\r"]
        if any(char in v for char in dangerous_chars):
            raise ValueError("Password contains invalid characters")
        return v


class StatusResponse(BaseModel):
    state: str
    ssid: str | None = None
    ip_address: str | None = None
    tunnel_url: str | None = None
    error: str | None = None
    session_id: str


class WebServer:
    def __init__(
        self, settings: Settings, network_manager: NetworkManager, state_manager: StateManager
    ):
        self.settings = settings
        self.network_manager = network_manager
        self.state_manager = state_manager
        self.captive_portal = CaptivePortal(
            interface=self.network_manager.wifi_device or "wlan0",
            gateway_ip=self.settings.ap_ip,
            web_port=self.settings.web_port,
        )
        self._connection_lock = asyncio.Lock()

        self.app = FastAPI(
            title="Distiller WiFi Setup",
            version="2.2.1",
            docs_url="/api/docs" if settings.debug else None,
            redoc_url="/api/redoc" if settings.debug else None,
        )

        template_dir = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=str(template_dir))
        static_dir = Path(__file__).parent.parent / "static"
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        self.websockets: dict[str, WebSocket] = {}
        self._setup_captive_portal_routes()
        self._setup_routes()
        self._setup_websocket()

    def _setup_captive_portal_routes(self):
        """Setup routes that respond to OS connectivity checks.

        All endpoints return 302 redirects to trigger captive portal detection.
        This works in combination with the wildcard DNS server.
        """

        @self.app.get("/generate_204")
        @self.app.get("/gen_204")
        async def android_captive_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/hotspot-detect.html")
        @self.app.get("/library/test/success.html")
        async def ios_captive_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/success.txt")
        async def ios_success_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/ncsi.txt")
        async def windows_ncsi_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/connecttest.txt")
        async def windows_connect_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/canonical.html")
        async def firefox_captive_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

        @self.app.get("/kindle-wifi/wifistub.html")
        async def kindle_captive_check(request: Request):
            return Response(
                status_code=302,
                headers={"Location": f"http://{self.settings.ap_ip}:{self.settings.web_port}/"},
            )

    def _setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            session_id = request.cookies.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())

            await self._track_session(session_id, request)
            state = self.state_manager.get_state()

            if state.connection_state == ConnectionState.CONNECTED:
                return self.templates.TemplateResponse(
                    "status.html",
                    {
                        "request": request,
                        "ssid": state.network_info.ssid,
                        "ip_address": state.network_info.ip_address,
                        "tunnel_url": state.tunnel_url,
                        "tunnel_provider": state.tunnel_provider,
                        "device_name": self.settings.mdns_hostname,
                        "port": self.settings.web_port,
                        "session_id": session_id,
                    },
                )

            networks = await self.network_manager.scan_networks()
            is_ap_mode = state.connection_state == ConnectionState.AP_MODE
            show_ap_message = is_ap_mode and not networks

            # Get current AP password from state or use default
            ap_password = state.ap_password or "setupwifi123"

            response = self.templates.TemplateResponse(
                "setup.html",
                {
                    "request": request,
                    "networks": networks,
                    "device_name": self.settings.mdns_hostname,
                    "ap_ssid": self.settings.ap_ssid,
                    "ap_password": ap_password,
                    "session_id": session_id,
                    "is_ap_mode": is_ap_mode,
                    "show_ap_message": show_ap_message,
                },
            )
            response.set_cookie("session_id", session_id, max_age=3600)
            return response

        @self.app.get("/api/status")
        async def get_status(request: Request) -> StatusResponse:
            session_id = request.cookies.get("session_id", str(uuid.uuid4()))
            state = self.state_manager.get_state()

            return StatusResponse(
                state=state.connection_state.value,
                ssid=state.network_info.ssid,
                ip_address=state.network_info.ip_address,
                tunnel_url=state.tunnel_url,
                error=state.error_message,
                session_id=session_id,
            )

        @self.app.get("/api/networks")
        async def get_networks() -> dict:
            state = self.state_manager.get_state()
            networks = await self.network_manager.scan_networks()

            is_ap_mode = state.connection_state == ConnectionState.AP_MODE

            return {
                "is_ap_mode": is_ap_mode,
                "networks": [
                    {
                        "ssid": net.ssid,
                        "signal": net.signal,
                        "security": net.security,
                        "in_use": net.in_use,
                    }
                    for net in networks
                ],
                "message": (
                    "Connect to the Access Point first to see available networks"
                    if is_ap_mode and not networks
                    else None
                ),
            }

        @self.app.post("/api/connect")
        async def connect_to_network(request: Request, conn_req: ConnectionRequest) -> JSONResponse:
            async with self._connection_lock:
                session_id = request.cookies.get("session_id", str(uuid.uuid4()))

                await self.state_manager.update_state(
                    connection_state=ConnectionState.CONNECTING,
                    network_info=NetworkInfo(ssid=conn_req.ssid),
                )

                await self._broadcast_status()
                asyncio.create_task(self._connect_to_network(conn_req.ssid, conn_req.password))

                return JSONResponse(
                    content={"status": "connecting", "session_id": session_id},
                    status_code=status.HTTP_202_ACCEPTED,
                )

        @self.app.post("/api/disconnect")
        async def disconnect_network(request: Request) -> JSONResponse:
            """Disconnect and return to AP mode."""
            session_id = request.cookies.get("session_id", str(uuid.uuid4()))

            # Start disconnection in background
            asyncio.create_task(self._disconnect_and_restart_ap())

            return JSONResponse(content={"status": "disconnecting", "session_id": session_id})

        @self.app.get("/health")
        async def health_check() -> JSONResponse:
            """Basic health check endpoint."""
            return JSONResponse(
                content={"status": "healthy", "service": "distiller-wifi"}, status_code=200
            )

        @self.app.get("/ready")
        async def readiness_check() -> JSONResponse:
            """Readiness check - verifies all services are operational."""
            checks = {
                "network_manager": self.network_manager.wifi_device is not None,
                "state_manager": self.state_manager.get_state() is not None,
                "web_server": True,  # If we're responding, web server is ready
            }

            all_ready = all(checks.values())
            return JSONResponse(
                content={
                    "ready": all_ready,
                    "checks": checks,
                    "state": self.state_manager.get_state().connection_state.value,
                },
                status_code=200 if all_ready else 503,
            )

        @self.app.post("/connect", response_class=HTMLResponse)
        async def connect_form(
            request: Request, ssid: str = Form(...), password: str | None = Form(None)
        ):
            """Handle form submission for WiFi connection."""
            session_id = request.cookies.get("session_id", str(uuid.uuid4()))

            # Validate input using the same validation as API
            try:
                validated = ConnectionRequest(ssid=ssid, password=password)
                ssid = validated.ssid
                password = validated.password
            except Exception as e:
                # Return error page
                return self.templates.TemplateResponse(
                    "setup.html",
                    {
                        "request": request,
                        "networks": await self.network_manager.scan_networks(),
                        "device_name": self.settings.mdns_hostname,
                        "session_id": session_id,
                        "error": str(e),
                    },
                )

            # Update state and start connection
            await self.state_manager.update_state(
                connection_state=ConnectionState.CONNECTING, network_info=NetworkInfo(ssid=ssid)
            )

            # Start connection in background
            asyncio.create_task(self._connect_to_network(ssid, password))

            # Show connecting page
            response = self.templates.TemplateResponse(
                "connecting.html",
                {
                    "request": request,
                    "ssid": ssid,
                    "session_id": session_id,
                    "device_name": self.settings.mdns_hostname,
                },
            )
            response.set_cookie("session_id", session_id, max_age=3600)
            return response

        @self.app.get("/status", response_class=HTMLResponse)
        async def status_page(request: Request):
            """Status page showing current connection details."""
            session_id = request.cookies.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())

            # Get current state
            state = self.state_manager.get_state()

            # If not connected, redirect to setup
            if state.connection_state != ConnectionState.CONNECTED:
                return self.templates.TemplateResponse(
                    "setup.html",
                    {
                        "request": request,
                        "networks": await self.network_manager.scan_networks(),
                        "device_name": self.settings.mdns_hostname,
                        "session_id": session_id,
                    },
                )

            # Show status page
            response = self.templates.TemplateResponse(
                "status.html",
                {
                    "request": request,
                    "ssid": state.network_info.ssid,
                    "ip_address": state.network_info.ip_address,
                    "signal_strength": state.network_info.signal_strength,
                    "tunnel_url": state.tunnel_url,
                    "tunnel_provider": state.tunnel_provider,
                    "device_name": self.settings.mdns_hostname,
                    "port": self.settings.web_port,
                    "session_id": session_id,
                },
            )
            response.set_cookie("session_id", session_id, max_age=3600)
            return response

    def _setup_websocket(self):
        """Setup WebSocket endpoint."""

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()

            # Generate session ID for this connection
            ws_id = str(uuid.uuid4())
            self.websockets[ws_id] = websocket

            try:
                # Send initial status
                state = self.state_manager.get_state()
                await websocket.send_json(
                    {
                        "type": "status",
                        "state": state.connection_state.value,
                        "ssid": state.network_info.ssid,
                        "ip_address": state.network_info.ip_address,
                        "tunnel_url": state.tunnel_url,
                        "tunnel_provider": state.tunnel_provider,
                        "error": state.error_message,
                    }
                )

                # Keep connection alive
                while True:
                    # Wait for messages (ping/pong)
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")

            except WebSocketDisconnect:
                logger.debug(f"WebSocket disconnected: {ws_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                # Remove from active connections
                self.websockets.pop(ws_id, None)

    async def _track_session(self, session_id: str, request: Request) -> None:
        """Track user session."""
        session = SessionInfo(
            session_id=session_id,
            created_at=datetime.now(),
            last_seen=datetime.now(),
        )
        await self.state_manager.add_session(session)

    async def _broadcast_status(self) -> None:
        """Broadcast status update to all WebSocket connections."""
        state = self.state_manager.get_state()
        message = {
            "type": "status",
            "state": state.connection_state.value,
            "ssid": state.network_info.ssid,
            "ip_address": state.network_info.ip_address,
            "tunnel_url": state.tunnel_url,
            "tunnel_provider": state.tunnel_provider,
            "error": state.error_message,
        }

        # Send to all connected clients
        disconnected = []
        for ws_id, websocket in self.websockets.items():
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(ws_id)

        # Clean up disconnected clients
        for ws_id in disconnected:
            self.websockets.pop(ws_id, None)

    async def _connect_to_network(self, ssid: str, password: str | None) -> None:
        """Handle network connection process."""
        try:
            # Attempt connection
            success = await self.network_manager.connect_to_network(ssid, password)

            if success:
                # Get connection info
                info = await self.network_manager.get_connection_info()

                # Update state
                await self.state_manager.update_state(
                    connection_state=ConnectionState.CONNECTED,
                    network_info=NetworkInfo(
                        ssid=ssid,
                        ip_address=info.get("ip_address") if info else None,
                        connected_at=datetime.now(),
                    ),
                    reset_retry=True,
                )

                logger.info(f"Successfully connected to {ssid}")
            else:
                # Connection failed
                await self.state_manager.update_state(
                    connection_state=ConnectionState.FAILED,
                    error_message="Failed to connect to network",
                    increment_retry=True,
                )

                # Return to AP mode after delay
                await asyncio.sleep(5)
                await self._restart_ap_mode()

            # Broadcast status update
            await self._broadcast_status()

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self.state_manager.update_state(
                connection_state=ConnectionState.FAILED, error_message=str(e)
            )
            await self._broadcast_status()

            # Return to AP mode
            await asyncio.sleep(5)
            await self._restart_ap_mode()

    async def _disconnect_and_restart_ap(self) -> None:
        """Disconnect from network and restart AP mode."""
        try:
            # Update state
            await self.state_manager.update_state(connection_state=ConnectionState.DISCONNECTED)

            # Disconnect from network
            await self.network_manager.disconnect_from_network()

            # Restart AP mode
            await self._restart_ap_mode()

        except Exception as e:
            logger.error(f"Disconnect error: {e}")

    async def _restart_ap_mode(self) -> None:
        """Restart Access Point mode."""
        try:
            # Check if existing password is still valid
            current_state = self.state_manager.get_state()
            ap_password = current_state.ap_password
            password_is_valid = False

            if ap_password and current_state.ap_password_generated_at:
                time_since_generation = (
                    datetime.now() - current_state.ap_password_generated_at
                ).total_seconds()
                password_is_valid = time_since_generation < self.settings.ap_password_ttl

            if password_is_valid:
                logger.info("=" * 50)
                logger.info(f"REUSING AP PASSWORD: {ap_password}")
                logger.info(
                    f"Password age: {int(time_since_generation)}s / TTL: {self.settings.ap_password_ttl}s"
                )
                logger.info("=" * 50)
            else:
                # Generate new password if none exists or TTL expired
                ap_password = generate_secure_password()
                logger.info("=" * 50)
                logger.info(f"NEW AP PASSWORD GENERATED: {ap_password}")
                logger.info("=" * 50)

                # Update state with new password and timestamp
                await self.state_manager.update_state(
                    ap_password=ap_password, ap_password_generated_at=datetime.now()
                )

            # Start AP mode with new password
            success = await self.network_manager.start_ap_mode(
                ssid=self.settings.ap_ssid,
                password=ap_password,
                ip_address=self.settings.ap_ip,
                channel=self.settings.ap_channel,
            )

            if success:
                await self.state_manager.update_state(
                    connection_state=ConnectionState.AP_MODE,
                    network_info=NetworkInfo(),
                    error_message=None,
                )
                logger.info(f"Returned to AP mode with password: {ap_password}")
            else:
                logger.error("Failed to restart AP mode")
                await self.state_manager.update_state(error_message="Failed to start Access Point")

            await self._broadcast_status()

        except Exception as e:
            logger.error(f"AP mode error: {e}")

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        return self.app

    async def enable_captive_portal(self):
        """Enable captive portal functionality."""
        if self.network_manager.wifi_device:
            self.captive_portal.interface = self.network_manager.wifi_device
        return await self.captive_portal.enable()

    async def disable_captive_portal(self):
        """Disable captive portal functionality."""
        return await self.captive_portal.disable()
