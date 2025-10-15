"""FastAPI web server with WebSocket support."""

import asyncio
import logging
import re
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI, Form, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from distiller_services.core.captive_portal import CaptivePortal
from distiller_services.core.config import Settings, generate_secure_password
from distiller_services.core.network_manager import NetworkManager
from distiller_services.core.state import ConnectionState, NetworkInfo, SessionInfo, StateManager
from distiller_services.paths import get_static_dir, get_templates_dir

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
        self._websocket_lock = asyncio.Lock()
        self._app_connection_lock: asyncio.Lock | None = None  # Will be set by DistillerWiFiApp

        self.app = FastAPI(
            title="Distiller WiFi Setup",
            version="3.0.0",
            docs_url="/api/docs" if settings.debug else None,
            redoc_url="/api/redoc" if settings.debug else None,
        )

        # Use dynamic paths
        template_dir = get_templates_dir()
        self.templates = Jinja2Templates(directory=str(template_dir))
        static_dir = get_static_dir()
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

        @self.app.get("/captive", response_class=HTMLResponse)
        async def captive_portal_page(request: Request):
            """Show captive portal proxy page.

            This page displays an iframe that proxies the captive portal through
            our server, allowing the user to authenticate using their phone's browser.
            """
            session_id = request.cookies.get("session_id", str(uuid.uuid4()))
            state = self.state_manager.get_state()

            # Get device IP
            device_ip = "unknown"
            if state.network_info and state.network_info.ip_address:
                device_ip = state.network_info.ip_address

            # Get portal URL
            portal_url = state.captive_portal_url or "http://detectportal.firefox.com"

            return self.templates.TemplateResponse(
                "captive_portal.html",
                {
                    "request": request,
                    "portal_url": portal_url,
                    "device_ip": device_ip,
                    "device_name": self.settings.mdns_hostname,
                    "session_id": session_id,
                },
            )

        @self.app.get("/api/proxy")
        async def proxy_request_get(request: Request, url: str | None = None):
            """Proxy HTTP GET requests to captive portal."""
            return await self._proxy_request(request, "GET", url)

        @self.app.post("/api/proxy")
        async def proxy_request_post(request: Request, url: str | None = None):
            """Proxy HTTP POST requests to captive portal."""
            return await self._proxy_request(request, "POST", url)

    def _render_error_template(
        self, error_type: str, message: str, details: str, suggestion: str
    ) -> str:
        """Render error page template."""
        state = self.state_manager.get_state()
        return self.templates.TemplateResponse(
            "error.html",
            {
                "request": {},
                "device_name": state.device_name,
                "error_type": error_type,
                "message": message,
                "details": details,
                "suggestion": suggestion,
            },
        ).body.decode()

    async def _proxy_request(
        self, request: Request, method: str, url: str | None = None
    ) -> Response:
        """Proxy HTTP requests to captive portal.

        This allows the user's browser to interact with the captive portal through
        our server, preserving cookies, headers, and session state.

        Args:
            request: FastAPI request object
            method: HTTP method (GET, POST, etc.)
            url: Target URL (from query param or state)

        Returns:
            Response with proxied content or HTML error page
        """
        state = self.state_manager.get_state()

        # Determine target URL
        if url and (url.startswith("http://") or url.startswith("https://")):
            target_url = url
        elif state.captive_portal_url:
            target_url = state.captive_portal_url
        else:
            error_html = self._render_error_template(
                "no_portal",
                "No Captive Portal Detected",
                "The device hasn't detected a captive portal on this network.",
                "Return to the setup page and try connecting to a different network.",
            )
            return Response(content=error_html, media_type="text/html")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0, verify=False
            ) as client:
                # Prepare headers (exclude host header to avoid conflicts)
                headers = dict(request.headers)
                headers.pop("host", None)
                headers.pop("content-length", None)  # Let httpx calculate this

                # Get request body for POST/PUT
                body = None
                if method in ["POST", "PUT"]:
                    body = await request.body()

                # Make proxied request
                response = await client.request(
                    method=method, url=target_url, headers=headers, content=body
                )

                # Prepare response headers (exclude some that shouldn't be proxied)
                response_headers = dict(response.headers)
                for header in ["content-encoding", "transfer-encoding", "connection"]:
                    response_headers.pop(header, None)

                # Return response to user
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                )

        except httpx.TimeoutException:
            logger.error(f"Proxy request timeout for {target_url}")
            error_html = self._render_error_template(
                "timeout",
                "Portal Not Responding",
                "The captive portal server is taking too long to respond.",
                "Check your WiFi signal strength and try refreshing the portal.",
            )
            return Response(content=error_html, media_type="text/html", status_code=504)

        except httpx.ConnectError as e:
            logger.error(f"Proxy connection failed for {target_url}: {e}")
            error_html = self._render_error_template(
                "connection_failed",
                "Cannot Reach Captive Portal",
                "Unable to establish connection to the portal server.",
                "Verify you're still connected to the WiFi network and try again.",
            )
            return Response(content=error_html, media_type="text/html", status_code=502)

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP error codes from the portal
            error_code = e.response.status_code
            if error_code == 401:
                message = "Authentication Required"
                details = "Portal requires valid credentials to continue."
                suggestion = "Please enter your username and password in the portal form."
            elif error_code == 403:
                message = "Authentication Failed"
                details = "Access denied - credentials may be invalid."
                suggestion = "Check your username/password and try again."
            elif error_code == 402:
                message = "Payment Required"
                details = "This network requires payment to access."
                suggestion = "Complete the payment process to gain internet access."
            else:
                message = f"Portal Error {error_code}"
                details = "The captive portal server returned an unexpected error."
                suggestion = "Try refreshing the portal or contact network support."

            logger.error(f"Proxy HTTP error {error_code} for {target_url}: {e}")
            error_html = self._render_error_template(
                f"http_{error_code}", message, details, suggestion
            )
            return Response(content=error_html, media_type="text/html", status_code=502)

        except Exception as e:
            logger.error(f"Proxy request failed for {target_url}: {e}")
            error_html = self._render_error_template(
                "unknown",
                "Unexpected Error Occurred",
                str(e),
                "Try refreshing the portal or return to setup.",
            )
            return Response(content=error_html, media_type="text/html", status_code=502)

    def _setup_websocket(self):
        """Setup WebSocket endpoint."""

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()

            # Generate session ID for this connection
            ws_id = str(uuid.uuid4())

            # Add to websockets dict with lock
            async with self._websocket_lock:
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
                        "connection_status": state.connection_status,
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
                # Remove from active connections with lock
                async with self._websocket_lock:
                    self.websockets.pop(ws_id, None)

    async def _track_session(self, session_id: str, request: Request) -> None:
        """Track user session."""
        session = SessionInfo(
            session_id=session_id,
            created_at=datetime.now(),
            last_seen=datetime.now(),
        )
        await self.state_manager.add_session(session)

    async def _broadcast_status(self, event_type: str = "status") -> None:
        """Broadcast status update to all WebSocket connections.

        Args:
            event_type: Type of event ("status" or "captive_portal_cleared")
        """
        state = self.state_manager.get_state()
        message = {
            "type": event_type,
            "state": state.connection_state.value,
            "ssid": state.network_info.ssid,
            "ip_address": state.network_info.ip_address,
            "tunnel_url": state.tunnel_url,
            "tunnel_provider": state.tunnel_provider,
            "error": state.error_message,
            "captive_portal_url": state.captive_portal_url,
            "connection_status": state.connection_status,
        }

        # Send to all connected clients with lock protection
        async with self._websocket_lock:
            disconnected = []
            for ws_id, websocket in list(self.websockets.items()):
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.append(ws_id)

            # Clean up disconnected clients
            for ws_id in disconnected:
                self.websockets.pop(ws_id, None)

    async def _connect_to_network(self, ssid: str, password: str | None) -> None:
        """Handle network connection process with granular status updates."""
        # Use app-level lock if available, otherwise use local lock
        connection_lock = self._app_connection_lock or self._connection_lock

        async with connection_lock:
            try:
                logger.info(f"User-initiated connection to {ssid}")

                # Update to connecting state
                await self.state_manager.update_state(
                    connection_status=f"Connecting to {ssid}...",
                    connection_progress=0.3,
                )
                await self._broadcast_status()

                # Attempt connection
                success = await self.network_manager.connect_to_network(ssid, password)

                if success:
                    # Get connection info
                    info = await self.network_manager.get_connection_info()

                    # Update progress after getting IP
                    await self.state_manager.update_state(
                        connection_status="Verifying connectivity...",
                        connection_progress=0.6,
                    )
                    await self._broadcast_status()

                    # Check for captive portal
                    is_captive, portal_url = await self.network_manager.detect_captive_portal()

                    if is_captive:
                        # Connected to WiFi but captive portal detected
                        logger.info(f"Captive portal detected: {portal_url}")

                        await self.state_manager.update_state(
                            connection_state=ConnectionState.CONNECTED,
                            network_info=NetworkInfo(
                                ssid=ssid,
                                ip_address=info.get("ip_address") if info else None,
                                connected_at=datetime.now(),
                            ),
                            captive_portal_url=portal_url,
                            captive_portal_detected_at=datetime.now(),
                            connection_progress=1.0,
                            connection_status="Captive portal detected - authentication required",
                            error_message="Captive portal detected - authentication required",
                            reset_retry=True,
                        )
                        logger.warning(
                            f"Connected to {ssid} but captive portal requires authentication"
                        )
                    else:
                        # Verify actual internet connectivity
                        await self.state_manager.update_state(
                            connection_status="Checking internet connectivity...",
                            connection_progress=0.8,
                        )
                        await self._broadcast_status()

                        has_internet = await self.network_manager.verify_connectivity()

                        # Connection complete
                        if has_internet:
                            await self.state_manager.update_state(
                                connection_state=ConnectionState.CONNECTED,
                                network_info=NetworkInfo(
                                    ssid=ssid,
                                    ip_address=info.get("ip_address") if info else None,
                                    connected_at=datetime.now(),
                                ),
                                connection_progress=1.0,
                                connection_status=None,  # Clear status on success
                                error_message=None,
                                reset_retry=True,
                            )
                            logger.info(f"Successfully connected to {ssid} with internet access")
                        else:
                            # WiFi connected but no internet (no captive portal detected)
                            await self.state_manager.update_state(
                                connection_state=ConnectionState.CONNECTED,
                                network_info=NetworkInfo(
                                    ssid=ssid,
                                    ip_address=info.get("ip_address") if info else None,
                                    connected_at=datetime.now(),
                                ),
                                connection_progress=1.0,
                                connection_status=None,  # Clear status
                                error_message="Limited connectivity - no internet access",
                                reset_retry=True,
                            )
                            logger.warning(f"Connected to {ssid} but no internet access")
                else:
                    # Connection failed - get user-friendly error message
                    error_msg = "Failed to connect to network"

                    # Try to get more specific error from network manager's last error
                    if hasattr(self.network_manager, "_last_connection_error"):
                        parsed_error = self.network_manager._parse_connection_error(
                            self.network_manager._last_connection_error
                        )
                        if parsed_error:
                            error_msg = parsed_error

                    logger.error(f"Connection to {ssid} failed: {error_msg}")

                    await self.state_manager.update_state(
                        connection_state=ConnectionState.FAILED,
                        error_message=error_msg,
                        connection_progress=0.0,
                        connection_status=None,  # Clear status on failure
                        increment_retry=True,
                    )
                    await self._broadcast_status()

                    # Return to AP mode after delay
                    await asyncio.sleep(5)
                    await self._restart_ap_mode()

                # Broadcast final status update
                await self._broadcast_status()

            except Exception as e:
                logger.error(f"Connection error: {e}", exc_info=True)
                await self.state_manager.update_state(
                    connection_state=ConnectionState.FAILED,
                    error_message=f"Connection error: {str(e)}",
                    connection_progress=0.0,
                    connection_status=None,  # Clear status on error
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

    async def monitor_captive_portal_auth(self) -> None:
        """Background task that monitors for successful captive portal authentication.

        Runs while captive_portal_url is set, checking connectivity every 10 seconds.
        When internet access is restored, clears the captive portal state and triggers
        display update to show normal connected screen.

        Also monitors for session expiry - if internet is lost after successful auth,
        it re-triggers the captive portal state.

        This task runs continuously in the background and should be started when the
        service initializes.
        """
        logger.info("Starting captive portal authentication monitor")
        last_had_internet = False

        while True:
            try:
                # Get current state
                state = self.state_manager.get_state()

                # Case 1: Captive portal detected - waiting for authentication
                if state.captive_portal_url and state.connection_state == ConnectionState.CONNECTED:
                    # Check if we now have internet access
                    has_internet = await self.network_manager.verify_connectivity()

                    if has_internet:
                        logger.info(
                            "Captive portal authentication successful - internet access restored"
                        )

                        # Clear captive portal state
                        await self.state_manager.update_state(
                            captive_portal_url=None,
                            captive_portal_detected_at=None,
                            captive_portal_session_expires_at=None,
                            error_message=None,
                        )

                        # Broadcast special event to WebSocket clients for captive portal success
                        await self._broadcast_status(event_type="captive_portal_cleared")

                        logger.info("Captive portal cleared, normal connectivity restored")
                        last_had_internet = True

                # Case 2: Connected to network - monitor for session expiry
                elif (
                    state.connection_state == ConnectionState.CONNECTED
                    and not state.captive_portal_url
                ):
                    # Check if internet is still accessible
                    has_internet = await self.network_manager.verify_connectivity()

                    # If we had internet before but lost it now, might be session expiry
                    if last_had_internet and not has_internet:
                        logger.warning(
                            "Internet connectivity lost - checking if captive portal session expired"
                        )

                        # Re-check for captive portal
                        is_captive, portal_url = await self.network_manager.detect_captive_portal()

                        if is_captive:
                            logger.warning(
                                "Captive portal session expired - re-authentication required"
                            )

                            # Set captive portal state again
                            await self.state_manager.update_state(
                                captive_portal_url=portal_url,
                                captive_portal_detected_at=datetime.now(),
                                error_message="Captive portal session expired - please re-authenticate",
                            )

                            # Broadcast update
                            await self._broadcast_status()

                            last_had_internet = False

                    elif has_internet:
                        last_had_internet = True

                # Check every 10 seconds
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Captive portal monitor error: {e}", exc_info=True)
                await asyncio.sleep(10)

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
