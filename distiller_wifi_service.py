"""
Distiller WiFi Service (Oneshot Mode)

Handles single-radio WiFi hardware limitation with proper state management,
web server coordination, and seamless user experience during transitions.
Runs as a oneshot service - exits after successful WiFi connection to free resources.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
import threading
import subprocess
from pathlib import Path
from typing import Optional
from enum import Enum

from network.wifi_manager import WiFiManager
from network.device_config import get_device_config
from network.session_manager import get_session_manager, SessionStatus
from display.eink_display import get_display

try:
    from flask import Flask, render_template, request, jsonify, redirect, url_for

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False



class ServiceState(Enum):
    """Service state definitions"""

    INITIALIZING = "initializing"
    HOTSPOT_MODE = "hotspot_mode"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class DistillerWiFiService:
    """Oneshot WiFi Setup Service with proper state transitions - exits after connection"""

    def __init__(
        self,
        hotspot_ssid: str = None,
        hotspot_password: str = None,
        device_name: str = None,
        web_port: int = None,
    ):
        # Initialize device configuration
        self.device_config = get_device_config()
        
        # Use device configuration with fallbacks to parameters
        self.hotspot_ssid = hotspot_ssid or self.device_config.get_hotspot_ssid()
        self.hotspot_password = hotspot_password or self.device_config.get_hotspot_password()
        self.device_name = device_name or self.device_config.get_friendly_name()
        self.web_port = web_port or self.device_config.get_web_port()

        # Service state
        self.current_state = ServiceState.INITIALIZING
        self.running = False
        self.target_ssid: Optional[str] = None
        self.target_password: Optional[str] = None
        self.connection_start_time: Optional[float] = None
        self._connection_in_progress = False  # Flag to prevent race conditions
        self.hotspot_ip: Optional[str] = None  # Store actual hotspot IP
        self._successful_connection_ip: Optional[str] = None  # Track successful connection IP
        self._successful_connection_ssid: Optional[str] = None  # Track successful connection SSID

        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Initialize WiFi manager
        self.wifi_manager = WiFiManager()

        # Initialize session manager
        self.session_manager = get_session_manager()
        
        # Initialize e-ink display
        self.display = get_display()

        # Flask app for web interface
        self.app = self._create_flask_app() if FLASK_AVAILABLE else None
        self.web_server_thread: Optional[threading.Thread] = None
        
        # Add custom template filters
        if self.app:
            self._add_template_filters()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.logger.info("Oneshot WiFi Service initialized")
        self.logger.info(f"Device ID: {self.device_config.get_device_id()}")
        self.logger.info(f"Hostname: {self.device_config.get_hostname()}")
        self.logger.info(f"Hotspot SSID: {self.hotspot_ssid}")
        self.logger.info(f"mDNS URL: {self.device_config.get_device_mdns_url()}")

    def setup_logging(self):
        """Configure logging"""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        # Try to write to system log first, fallback to local
        log_paths = ["/var/log/distiller-wifi.log", "./distiller-wifi.log"]
        log_file = None

        for path in log_paths:
            try:
                Path(path).touch(exist_ok=True)
                log_file = path
                break
            except (PermissionError, OSError):
                continue

        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file:
            handlers.append(logging.FileHandler(log_file))

        # Production logging level - only INFO and above
        logging.basicConfig(
            level=logging.INFO, format=log_format, handlers=handlers, force=True
        )

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals for oneshot service"""
        self.logger.info(f"Received signal {signum}, shutting down oneshot service...")
        self.running = False

    def _create_flask_app(self) -> Flask:
        """Create Flask web application"""
        app = Flask(__name__, template_folder="templates", static_folder="static")

        # Disable caching
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

        @app.after_request
        def add_no_cache_headers(response):
            response.cache_control.max_age = 0
            response.cache_control.no_cache = True
            response.cache_control.must_revalidate = True
            
            # Add security headers to handle HTTPS-Only mode and CSP
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # Allow HTTP requests for local IoT device operation (no HTTPS upgrade)
            response.headers['Content-Security-Policy'] = (
                "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http: https:; "
                "connect-src 'self' http: https: ws: wss:; "
                "img-src 'self' data: blob: http: https:; "
                "font-src 'self' data: http: https:; "
                "frame-src 'none'; "
                "object-src 'none'"
            )
            
            # For local development and IoT devices, allow mixed content
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            
            return response

        # Routes
        @app.route("/")
        def index():
            return self._handle_index()

        @app.route("/confirm")
        def confirm():
            return self._handle_confirm()

        @app.route("/connect", methods=["POST"])
        def connect():
            return self._handle_connect()

        @app.route("/status")
        def status():
            return self._handle_status()

        @app.route("/api/status")
        def api_status():
            return self._handle_api_status()

        @app.route("/api/networks")
        def api_networks():
            return self._handle_api_networks()

        @app.route("/api/connect", methods=["POST"])
        def api_connect():
            return self._handle_connect()

        @app.route("/api/scan", methods=["GET"])
        def api_scan():
            """Manually trigger network scan"""
            try:
                networks = asyncio.run(self._scan_networks_properly())
                return jsonify(
                    {
                        "success": True,
                        "networks": [
                            {
                                "ssid": net.ssid,
                                "signal_strength": net.signal,
                                "security": net.security,
                                "frequency": net.frequency,
                            }
                            for net in networks
                        ],
                    }
                )
            except Exception as e:
                self.logger.error(f"Error in API scan: {e}")
                return jsonify({"success": False, "error": str(e)}), 500

        @app.route("/refresh-display")
        def refresh_display():
            """Refresh e-ink display with current WiFi info"""
            try:
                if self.current_state == ServiceState.CONNECTED:
                    # Get current WiFi info and update display
                    from network.network_utils import NetworkUtils
                    network_utils = NetworkUtils()
                    wifi_name = network_utils.get_wifi_name()
                    ip_address = network_utils.get_wifi_ip_address()
                    signal_strength = network_utils.get_wifi_signal_strength()
                    
                    self.display.display_info_screen(wifi_name, ip_address, signal_strength)
                    return jsonify({"success": True, "message": "Display refreshed"})
                else:
                    return jsonify(
                        {
                            "success": False,
                            "message": "Display not available or not connected",
                        }
                    )
            except Exception as e:
                self.logger.error(f"Error refreshing display: {e}")
                return jsonify({"success": False, "error": str(e)}), 500

        @app.route("/api/setup-status/<session_id>")
        def api_setup_status(session_id):
            """Get setup status for specific session"""
            return self._handle_api_setup_status(session_id)

        @app.route("/setup/success/<session_id>")
        def setup_success(session_id):
            """Show success page for specific session"""
            return self._handle_setup_success(session_id)

        @app.route("/api/session/validate", methods=["POST"])
        def api_session_validate():
            """Validate and refresh session"""
            return self._handle_api_session_validate()

        @app.route("/api/session/stats")
        def api_session_stats():
            """Get session statistics (for debugging)"""
            return self._handle_api_session_stats()

        # Catch-all for captive portal
        @app.route("/<path:path>")
        def catch_all(path):
            self.logger.info(f"Redirecting path: {path}")
            return redirect(url_for("index"))

        return app


    def _add_template_filters(self):
        """Add custom template filters"""
        @self.app.template_filter('timestamp_to_time')
        def timestamp_to_time(timestamp):
            """Convert timestamp to readable time format"""
            try:
                from datetime import datetime
                dt = datetime.fromtimestamp(float(timestamp))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                return 'Unknown time'

    def _handle_index(self):
        """Handle main index page"""
        try:
            if self.current_state == ServiceState.HOTSPOT_MODE:
                # Don't scan networks on page load - let JavaScript handle it
                # This prevents automatic hotspot restarts
                return render_template(
                    "index.html",
                    networks=[],  # Empty initially, will be loaded by JavaScript
                    device_name=self.device_name,
                    current_state=self.current_state.value,
                    web_port=self.web_port,
                )
            elif self.current_state == ServiceState.CONNECTED:
                # Show connected status
                return redirect(url_for("status"))
            elif self.current_state == ServiceState.INITIALIZING:
                # Service is transitioning (e.g., changing networks)
                # Redirect to status page to show progress
                return redirect(url_for("status"))
            else:
                # Show loading or error state
                return render_template(
                    "index.html",
                    networks=[],
                    device_name=self.device_name,
                    current_state=self.current_state.value,
                    message="Service initializing...",
                    web_port=self.web_port,
                )
        except Exception as e:
            self.logger.error(f"Error in index handler: {e}")
            return render_template(
                "index.html",
                networks=[],
                device_name=self.device_name,
                error="Failed to load networks",
                web_port=self.web_port,
            )

    def _handle_confirm(self):
        """Handle network confirmation page"""
        try:
            ssid = request.args.get("ssid", "")
            encrypted = request.args.get("encrypted", "unencrypted")

            if not ssid:
                return redirect(url_for("index"))

            return render_template(
                "confirm.html",
                ssid=ssid,
                encrypted=encrypted,
                device_name=self.device_name,
                web_port=self.web_port,
            )
        except Exception as e:
            self.logger.error(f"Error in confirm handler: {e}")
            return redirect(url_for("index"))

    def _handle_connect(self):
        """Handle connection request"""
        try:
            self.logger.debug(f"Raw request data: {request.data}")
            self.logger.debug(f"Request content type: {request.content_type}")
            self.logger.debug(f"Request is_json: {request.is_json}")
            self.logger.debug(f"Request form: {request.form}")
            self.logger.debug(f"Request args: {request.args}")

            # Handle both form data and JSON data
            if request.is_json:
                data = request.get_json()
                self.logger.debug(f"JSON data: {data}")
                ssid = data.get("ssid", "") if data else ""
                password = data.get("password", "") if data else ""
            else:
                ssid = request.form.get("ssid", "")
                password = request.form.get("password", "")

            self.logger.info(
                f"Connection request received: SSID='{ssid}', Password={'***' if password else 'None'}"
            )

            if not ssid:
                self.logger.warning("No SSID provided in connection request")
                if request.is_json:
                    return jsonify({"success": False, "error": "No SSID provided"}), 400
                return redirect(url_for("index"))

            # Create setup session
            user_agent = request.headers.get('User-Agent', 'Unknown')
            session_id = self.session_manager.create_session(
                target_ssid=ssid,
                user_agent=user_agent
            )

            # Store connection target
            self.target_ssid = ssid
            self.target_password = password
            self.connection_start_time = time.time()

            self.logger.info(f"Starting connection process to '{ssid}' in background (session: {session_id})")

            # Update session status to connecting
            self.session_manager.update_session_status(session_id, SessionStatus.CONNECTING)

            # Start connection in background
            self._start_connection_background(session_id)

            if request.is_json:
                return jsonify({"success": True, "message": "Connection started", "session_id": session_id})
            
            # Instead of immediately redirecting to status, show a connecting page
            # that will handle the hotspot disconnection gracefully
            return render_template(
                "connecting.html",
                ssid=ssid,
                device_name=self.device_name,
                web_port=self.web_port,
                hotspot_ip=self.hotspot_ip or "192.168.4.1",
                session_id=session_id,  # Pass session ID to template
                device_id=self.device_config.get_device_id(),
            )

        except Exception as e:
            self.logger.error(f"Error in connect handler: {e}")
            if request.is_json:
                return jsonify({"success": False, "error": str(e)}), 500
            return redirect(url_for("index"))

    def _handle_status(self):
        """Handle status page"""
        try:
            # Get current status
            status_info = self._get_current_status()

            return render_template(
                "status.html",
                status=status_info,
                device_name=self.device_name,
                web_port=self.web_port,
            )
        except Exception as e:
            self.logger.error(f"Error in status handler: {e}")
            return render_template(
                "status.html",
                status={
                    "connected": False,
                    "connecting": False,
                    "error": "Status unavailable"
                },
                device_name=self.device_name,
                web_port=self.web_port,
            )

    def _handle_api_status(self):
        """Handle status API endpoint"""
        try:
            status_info = self._get_current_status()
            
            # Log response data for troubleshooting
            self.logger.info(f"API Status response: connected_to_target={status_info.get('connected_to_target')}, "
                            f"current_state={status_info.get('current_state')}, "
                            f"ssid={status_info.get('ssid')}, "
                            f"ip={status_info.get('ip_address')}")
            
            return jsonify({"success": True, **status_info})
        except Exception as e:
            self.logger.error(f"Error in API status: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    def _handle_api_networks(self):
        """Handle API request for available networks"""
        try:
            # Don't scan networks if we're in the middle of a connection
            if self.current_state == ServiceState.CONNECTING:
                self.logger.info(
                    "Connection in progress, returning cached/empty network list"
                )
                return jsonify(
                    {
                        "success": True,
                        "networks": [],
                        "message": "Connection in progress",
                    }
                )

            # Use cached or simplified scan for hotspot mode
            if self.current_state == ServiceState.HOTSPOT_MODE:
                # Don't stop hotspot for network scan - use a simpler approach
                try:
                    # Get a quick scan without stopping hotspot
                    networks = asyncio.run(self._get_networks_without_hotspot_restart())
                    return jsonify(
                        {
                            "success": True,
                            "networks": [
                                {
                                    "ssid": net.ssid,
                                    "signal_strength": net.signal,
                                    "security": net.security,
                                    "frequency": net.frequency,
                                }
                                for net in networks
                            ],
                        }
                    )
                except Exception as e:
                    self.logger.error(f"Error getting networks: {e}")
                    # Return some common networks as fallback
                    return jsonify(
                        {
                            "success": True,
                            "networks": [],
                            "message": "Scan temporarily unavailable",
                        }
                    )
            else:
                # Normal scan when not in hotspot mode
                networks = asyncio.run(self.wifi_manager.get_available_networks())
                return jsonify(
                    {
                        "success": True,
                        "networks": [
                            {
                                "ssid": net.ssid,
                                "signal_strength": net.signal,
                                "security": net.security,
                                "frequency": net.frequency,
                            }
                            for net in networks
                        ],
                    }
                )
        except Exception as e:
            self.logger.error(f"Error in API networks: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    def _handle_api_setup_status(self, session_id: str):
        """Handle setup status API request for specific session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return jsonify({"success": False, "error": "Session not found or expired"}), 404
            
            # Get current WiFi status
            status_info = self._get_current_status()
            
            # Combine session data with current status
            response_data = {
                "success": True,
                "session": session.to_dict(),
                "current_status": status_info,
                "device_info": {
                    "device_id": self.device_config.get_device_id(),
                    "hostname": self.device_config.get_hostname(),
                    "mdns_url": self.device_config.get_device_mdns_url(),
                }
            }
            
            # If session is connected and current status matches, include success redirect
            if (session.status == SessionStatus.CONNECTED and 
                status_info.get("connected_to_target", False)):
                response_data["redirect_to_success"] = True
                response_data["success_url"] = f"/setup/success/{session_id}"
            
            return jsonify(response_data)
            
        except Exception as e:
            self.logger.error(f"Error in setup status API: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    def _handle_setup_success(self, session_id: str):
        """Handle success page request for specific session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return render_template("error.html", 
                                     error="Session not found or expired",
                                     device_name=self.device_name), 404
            
            # Only show success page if session is actually connected
            if session.status != SessionStatus.CONNECTED:
                return redirect(url_for("index"))
            
            # Get current status and connection details
            status_info = self._get_current_status()
            connection_details = session.connection_details or {}
            
            # Prepare template data
            template_data = {
                "device_name": self.device_name,
                "device_id": self.device_config.get_device_id(),
                "hostname": self.device_config.get_hostname(),
                "session": session.to_dict(),
                "connection": connection_details,
                "current_status": status_info,
                "mdns_url": self.device_config.get_device_mdns_url(),
                "web_port": self.web_port,
                "tunnel_info": self._get_tunnel_info(),  # Will implement this
            }
            
            # Mark success page as cached
            self.session_manager.mark_success_page_cached(session_id)
            
            return render_template("success.html", **template_data)
            
        except Exception as e:
            self.logger.error(f"Error in setup success: {e}")
            return render_template("error.html", 
                                 error="Failed to load success page",
                                 device_name=self.device_name), 500

    def _handle_api_session_validate(self):
        """Handle session validation API request"""
        try:
            data = request.get_json() or {}
            session_id = data.get("session_id")
            
            if not session_id:
                return jsonify({"success": False, "error": "Session ID required"}), 400
            
            session = self.session_manager.get_session(session_id)
            if not session:
                return jsonify({"success": False, "error": "Session not found or expired"}), 404
            
            # Session is valid, return current status
            return jsonify({
                "success": True,
                "session": session.to_dict(),
                "valid": True,
                "message": "Session is valid"
            })
            
        except Exception as e:
            self.logger.error(f"Error in session validate: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    def _handle_api_session_stats(self):
        """Handle session statistics API request (for debugging)"""
        try:
            stats = self.session_manager.get_session_stats()
            return jsonify({"success": True, "stats": stats})
        except Exception as e:
            self.logger.error(f"Error in session stats: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    def _get_tunnel_info(self) -> dict:
        """Get tunnel information if available"""
        # This will be enhanced when we integrate with tunnel service
        # For now, return placeholder
        return {
            "available": False,
            "url": None,
            "qr_code": None,
            "status": "starting"
        }



    def _get_current_status(self) -> dict:
        """Get current service status"""
        try:
            # Get WiFi connection status with timeout and error handling
            try:
                wifi_status = asyncio.run(self.wifi_manager.get_connection_status())
            except Exception as wifi_error:
                self.logger.warning(f"WiFi status check failed: {wifi_error}")
                # During network transition, if we're in CONNECTED state, trust that state
                if self.current_state == ServiceState.CONNECTED:
                    self.logger.info("WiFi status check failed but service state is CONNECTED - assuming successful connection")
                    # Use stored connection info if available
                    connection_ip = self._successful_connection_ip or self.device_config.get_device_mdns_id()
                    connection_ssid = self._successful_connection_ssid or self.target_ssid
                    return {
                        "connected": True,
                        "connected_to_target": True,  # Trust the CONNECTED state
                        "connected_to_hotspot": False,
                        "connecting": False,
                        "ssid": connection_ssid,
                        "ip_address": connection_ip,
                        "interface": None,
                        "current_state": self.current_state.value,
                        "target_ssid": self.target_ssid,
                        "elapsed": 0,

                        "timestamp": int(time.time()),
                        "device_id": self.device_config.get_device_id(),
                        "mdns_url": self.device_config.get_device_mdns_url(),
                        "hostname": self.device_config.get_hostname(),
                        "message": "Network transition in progress"
                    }
                # Return status based on service state when WiFi check fails
                return self._get_fallback_status()

            # Determine service state
            connecting = (
                self.current_state == ServiceState.CONNECTING
                and self.connection_start_time
                and time.time() - self.connection_start_time < 120
            )  # 2 min timeout

            # Check if we're connected to a target network (not hotspot)
            connected_to_target = (
                wifi_status.connected 
                and self.current_state == ServiceState.CONNECTED
                and wifi_status.ssid 
                and not wifi_status.ssid.startswith(self.hotspot_ssid)  # Not connected to our hotspot
                and wifi_status.ip_address
                and wifi_status.ip_address != self.hotspot_ip  # Not using hotspot IP
                and self.target_ssid  # We have a target SSID
                and (wifi_status.ssid == self.target_ssid or wifi_status.ssid.startswith(self.target_ssid + " "))  # Connected to target (handle NetworkManager numbering)
            )

            # CRITICAL FIX: If we're in CONNECTED state but WiFi status doesn't show connection,
            # trust the service state (this handles network transition timing issues)
            if self.current_state == ServiceState.CONNECTED and not connected_to_target:
                self.logger.info(f"Service state is CONNECTED but WiFi status check inconsistent - trusting service state")
                self.logger.info(f"  WiFi Status: connected={wifi_status.connected}, ssid='{wifi_status.ssid}', target_ssid='{self.target_ssid}'")
                connected_to_target = True

            # Check if we're connected to hotspot
            connected_to_hotspot = (
                wifi_status.connected 
                and wifi_status.ssid 
                and (wifi_status.ssid.startswith(self.hotspot_ssid) or wifi_status.ip_address == self.hotspot_ip)
            )

            connected = connected_to_target or connected_to_hotspot



            return {
                "connected": connected,
                "connected_to_target": connected_to_target,  # New field to distinguish target vs hotspot
                "connected_to_hotspot": connected_to_hotspot,  # New field 
                "connecting": connecting,
                "ssid": wifi_status.ssid,
                "ip_address": wifi_status.ip_address,
                "interface": wifi_status.interface,
                "current_state": self.current_state.value,
                "target_ssid": self.target_ssid,
                "elapsed": (
                    time.time() - self.connection_start_time
                    if self.connection_start_time
                    else 0
                ),

                "timestamp": int(time.time()),
                "device_id": self.device_config.get_device_id(),
                "mdns_url": self.device_config.get_device_mdns_url(),
                "hostname": self.device_config.get_hostname(),
            }

        except Exception as e:
            self.logger.error(f"Error getting status: {e}")
            return self._get_fallback_status()

    def _get_fallback_status(self) -> dict:
        """Get fallback status when WiFi status check fails"""
        # Return status based on current service state
        if self.current_state == ServiceState.HOTSPOT_MODE:
            return {
                "connected": True,  # Connected to hotspot
                "connected_to_target": False,  # Not connected to target network
                "connected_to_hotspot": True,  # Connected to hotspot
                "connecting": False,
                "ssid": self.hotspot_ssid,  # Use hotspot SSID
                "ip_address": self.hotspot_ip or "192.168.4.1",  # Use actual hotspot IP
                "interface": None,
                "current_state": self.current_state.value,
                "target_ssid": self.target_ssid,
                "elapsed": 0,
                "timestamp": int(time.time()),
                "message": "Hotspot mode active",
                "device_id": self.device_config.get_device_id(),
                "mdns_url": self.device_config.get_device_mdns_url(),
                "hostname": self.device_config.get_hostname(),
            }
        elif self.current_state == ServiceState.CONNECTING:
            return {
                "connected": False,
                "connected_to_target": False,
                "connected_to_hotspot": False,
                "connecting": True,
                "ssid": self.target_ssid,
                "ip_address": None,
                "interface": None,
                "current_state": self.current_state.value,
                "target_ssid": self.target_ssid,
                "elapsed": (
                    time.time() - self.connection_start_time
                    if self.connection_start_time
                    else 0
                ),
                "timestamp": int(time.time()),
                "message": "Connection in progress",
                "device_id": self.device_config.get_device_id(),
                "mdns_url": self.device_config.get_device_mdns_url(),
                "hostname": self.device_config.get_hostname(),
            }
        else:
            # Default disconnected state
            return {
                "connected": False,
                "connected_to_target": False,
                "connected_to_hotspot": False,
                "connecting": False,
                "ssid": None,
                "ip_address": None,
                "interface": None,
                "current_state": self.current_state.value,
                "target_ssid": self.target_ssid,
                "elapsed": 0,
                "timestamp": int(time.time()),
                "message": "Disconnected",
                "device_id": self.device_config.get_device_id(),
                "mdns_url": self.device_config.get_device_mdns_url(),
                "hostname": self.device_config.get_hostname(),
            }

    def _start_connection_background(self, session_id: str):
        """Start connection process in background thread"""

        def connection_worker():
            try:
                self._connection_in_progress = True
                self.logger.info(f"Background connection thread started for session {session_id}")
                asyncio.run(self._perform_connection(session_id))
            except Exception as e:
                self.logger.error(f"Connection background thread error: {e}")
                # Mark session as failed
                self.session_manager.update_session_status(session_id, SessionStatus.FAILED)
            finally:
                self._connection_in_progress = False
                self.logger.info("Connection background thread finished")

        thread = threading.Thread(target=connection_worker, daemon=True)
        thread.start()
        self.logger.info("Connection background thread launched")

    async def _perform_connection(self, session_id: str):
        """Perform WiFi connection with proper state management"""
        try:
            if not self.target_ssid:
                self.session_manager.update_session_status(session_id, SessionStatus.FAILED)
                return

            self.logger.info(f"Starting connection to {self.target_ssid} (session: {session_id})")
            self.current_state = ServiceState.CONNECTING

            # Update e-ink display
            self.display.display_connecting_screen(self.target_ssid)

            # CRITICAL: Stop hotspot first before attempting connection
            if self.wifi_manager.is_hotspot_active():
                self.logger.info("Stopping hotspot before connecting to target network")
                await self.wifi_manager.stop_hotspot()
                # Wait for interface to be ready
                await asyncio.sleep(3)

            # Perform the connection (hotspot is now stopped)
            # Handle None password properly
            password = self.target_password or ""
            success = await self.wifi_manager.connect_to_network(
                self.target_ssid, password
            )

            if success:
                self.logger.info(f"Initial connection successful to {self.target_ssid}")
                
                # Wait for connection to stabilize before marking as fully connected
                self.logger.info("Waiting for connection to stabilize...")
                await asyncio.sleep(5)  # Wait for DHCP and network setup
                
                # Verify connection is still active and stable
                verification_attempts = 3
                for attempt in range(verification_attempts):
                    status = await self.wifi_manager.get_connection_status()
                    if status.connected and status.ip_address:
                        self.logger.info(f"Connection verified (attempt {attempt + 1}): {status.ip_address}")
                        break
                    else:
                        self.logger.warning(f"Connection verification failed (attempt {attempt + 1})")
                        if attempt < verification_attempts - 1:
                            await asyncio.sleep(3)
                else:
                    # All verification attempts failed
                    self.logger.error("Connection verification failed, treating as failed connection")
                    await self._start_hotspot_mode()
                    return
                
                # Connection is stable, mark as connected
                self.current_state = ServiceState.CONNECTED
                self.logger.info(f"Connection to {self.target_ssid} fully established and stable")
                
                # CRITICAL: Store connection info for status API during transition
                self._successful_connection_ip = status.ip_address
                self._successful_connection_ssid = self.target_ssid

                # Update session status to connected with connection details
                connection_details = {
                    "ssid": self.target_ssid,
                    "ip_address": status.ip_address,
                    "interface": status.interface,
                    "connected_at": time.time()
                }
                self.session_manager.update_session_status(
                    session_id, SessionStatus.CONNECTED, connection_details
                )

                # Update e-ink display with success message
                self.display.display_success_screen(self.target_ssid, "Connected")
                # The pinggy tunnel service will handle detailed display updates once connected

                # Handle network transition
                await self._handle_network_transition()

            else:
                self.logger.error(f"Failed to connect to {self.target_ssid}")
                
                # Update session status to failed
                self.session_manager.update_session_status(session_id, SessionStatus.FAILED)

                # Restore hotspot mode after connection failure
                self.logger.info("Restoring hotspot mode after connection failure")
                await self._start_hotspot_mode()

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            # Mark session as failed
            self.session_manager.update_session_status(session_id, SessionStatus.FAILED)
            # Restore hotspot mode on error
            await self._start_hotspot_mode()
        finally:
            self.target_ssid = None
            self.target_password = None
            self.connection_start_time = None

    async def _handle_network_transition(self):
        """Handle transition from hotspot to client network"""
        try:
            # Get new network status
            status = await self.wifi_manager.get_connection_status()

            if status.connected and status.ip_address:
                self.logger.info(f"Network transition: now at {status.ip_address}")

                # Use transition method to properly handle mDNS service move to new network
                mdns_success = self.device_config.transition_mdns_to_network(status.ip_address)
                if mdns_success:
                    mdns_url = self.device_config.get_device_mdns_url()
                    self.logger.info(f"mDNS service updated for new network: {mdns_url}")
                else:
                    self.logger.warning("Failed to update mDNS service for new network")

                # Web server will continue running on all interfaces
                # The status page will handle redirection to new IP

                # Log success
                self.logger.info(f"WiFi setup completed successfully")
                self.logger.info(
                    f"Device accessible at: http://{status.ip_address}:{self.web_port}"
                )
                
                # Also log mDNS URL for convenience
                mdns_url = self.device_config.get_device_mdns_url()
                self.logger.info(f"Device also accessible via mDNS: {mdns_url}")

                # Start pinggy tunnel service after successful WiFi connection
                self.logger.info("Starting pinggy tunnel service for remote access")
                self._start_pinggy_tunnel_service()

        except Exception as e:
            self.logger.error(f"Error handling network transition: {e}")

    def _start_pinggy_tunnel_service(self):
        """Start the pinggy tunnel service after successful WiFi connection"""
        try:
            # Check if pinggy tunnel service is already running
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', 'pinggy-tunnel.service'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip() == 'active':
                    self.logger.info("Pinggy tunnel service is already running")
                    # Restart it to ensure it's fresh
                    self.logger.info("Restarting pinggy tunnel service")
                    subprocess.run(
                        ['systemctl', 'restart', 'pinggy-tunnel.service'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                else:
                    self.logger.info("Pinggy tunnel service is not running, starting it")
            except subprocess.TimeoutExpired:
                self.logger.warning("Timeout checking pinggy tunnel service status")
            except Exception as e:
                self.logger.warning(f"Could not check pinggy tunnel service status: {e}")

            # Start the pinggy tunnel service
            self.logger.info("Starting pinggy tunnel service for remote access")
            try:
                result = subprocess.run(
                    ['systemctl', 'start', 'pinggy-tunnel.service'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self.logger.info("Pinggy tunnel service started successfully")
                    # Enable it for future boots
                    subprocess.run(
                        ['systemctl', 'enable', 'pinggy-tunnel.service'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                else:
                    self.logger.warning(f"Failed to start pinggy tunnel service: {result.stderr}")
            except subprocess.TimeoutExpired:
                self.logger.error("Timeout starting pinggy tunnel service")
            except Exception as e:
                self.logger.error(f"Error starting pinggy tunnel service: {e}")

        except Exception as e:
            self.logger.error(f"Unexpected error starting pinggy tunnel service: {e}")

    async def check_initial_state(self) -> ServiceState:
        """Check initial state and determine startup mode"""
        try:
            self.logger.info("Checking initial WiFi state...")

            status = await self.wifi_manager.get_connection_status()

            if status.connected:
                if status.ssid and status.ssid.startswith(self.hotspot_ssid):
                    # Connected to our hotspot - stay in hotspot mode
                    self.logger.info(f"Connected to setup hotspot: {status.ssid}")
                    return ServiceState.HOTSPOT_MODE
                else:
                    # Connected to real network - connected mode
                    self.logger.info(f"Already connected to: {status.ssid}")
                    return ServiceState.CONNECTED
            else:
                # No connection - start hotspot mode
                self.logger.info("No WiFi connection detected")
                return ServiceState.HOTSPOT_MODE

        except Exception as e:
            self.logger.error(f"Error checking initial state: {e}")
            return ServiceState.HOTSPOT_MODE

    async def _start_hotspot_mode(self):
        """Start hotspot mode"""
        try:
            self.logger.info("Starting hotspot mode")
            self.current_state = ServiceState.HOTSPOT_MODE

            success, hotspot_ip = await self.wifi_manager.start_hotspot(
                self.hotspot_ssid, self.hotspot_password
            )

            if success:
                self.hotspot_ip = hotspot_ip
                self.logger.info(f"Hotspot started: {self.hotspot_ssid}")
                self.logger.info(
                    f"Web interface: http://{hotspot_ip}:{self.web_port}"
                )
                
                # Start mDNS service for device discovery
                mdns_success = self.device_config.start_mdns_service(hotspot_ip or "192.168.4.1", self.web_port)
                if mdns_success:
                    mdns_url = self.device_config.get_device_mdns_url()
                    self.logger.info(f"mDNS service started: {mdns_url}")
                else:
                    self.logger.warning("Failed to start mDNS service")

                # Update e-ink display with setup information
                self.display.display_setup_screen(
                    self.hotspot_ssid,
                    self.hotspot_password, 
                    self.hotspot_ip or "192.168.4.1",
                    self.web_port
                )

            else:
                self.logger.error("Failed to start hotspot")
                self.current_state = ServiceState.ERROR

        except Exception as e:
            self.logger.error(f"Error starting hotspot: {e}")
            self.current_state = ServiceState.ERROR

    async def _transition_to_hotspot(self):
        """Transition from connected state back to hotspot mode"""
        try:
            self.logger.info("Transitioning to hotspot mode for network change")

            # Get current connection status
            current_status = await self.wifi_manager.get_connection_status()
            if current_status.connected:
                self.logger.info(
                    f"Disconnecting from current network: {current_status.ssid}"
                )

                # Stop current connection - this will automatically disconnect
                # We don't need to explicitly disconnect since starting hotspot will handle it

            # Start hotspot mode
            await self._start_hotspot_mode()

            self.logger.info("Successfully transitioned to hotspot mode")

        except Exception as e:
            self.logger.error(f"Error transitioning to hotspot: {e}")
            # Try to ensure we end up in some usable state
            try:
                await self._start_hotspot_mode()
            except Exception as fallback_error:
                self.logger.error(f"Fallback hotspot start failed: {fallback_error}")
                self.current_state = ServiceState.ERROR

    def _start_web_server(self):
        """Start web server in background thread"""
        if not FLASK_AVAILABLE or not self.app:
            self.logger.error("Flask not available, cannot start web server")
            return

        def run_server():
            # Show the mDNS URL for user convenience
            mdns_url = self.device_config.get_device_mdns_url()
            accessible_ip = self.hotspot_ip or "0.0.0.0"
            self.logger.info(f"Starting web server on {accessible_ip}:{self.web_port}")
            self.logger.info(f"Device accessible via mDNS: {mdns_url}")
            if self.app:  # Additional None check for type safety
                self.app.run(
                    host="0.0.0.0",
                    port=self.web_port,
                    debug=False,
                    use_reloader=False,
                    threaded=True,
                )

        self.web_server_thread = threading.Thread(target=run_server, daemon=True)
        self.web_server_thread.start()





    async def run(self):
        """Run the WiFi service in oneshot mode - exits after successful connection"""
        self.logger.info("Starting Distiller WiFi Service (Oneshot Mode)")
        self.running = True

        try:
            # Check initial state
            initial_state = await self.check_initial_state()
            self.current_state = initial_state

            # If already connected, show current WiFi info then exit with success
            if initial_state == ServiceState.CONNECTED:
                self.logger.info("Already connected to WiFi network - displaying current info before exit")
                
                # Update e-ink display with current WiFi information
                if self.enable_eink:
                    try:
                        self._update_eink_info()
                        self.logger.info("E-ink display updated with current WiFi information")
                        # Small delay to ensure display update completes
                        await asyncio.sleep(3)
                    except Exception as e:
                        self.logger.error(f"Error updating e-ink display: {e}")
                
                self.logger.info("WiFi info display complete - oneshot service complete")
                return

            # If disconnected, start hotspot mode and wait for configuration
            if initial_state == ServiceState.HOTSPOT_MODE:
                await self._start_hotspot_mode()
                
                # Start web server for user interaction
                self._start_web_server()
                
                self.logger.info("WiFi setup service ready - waiting for user configuration")
                
                # Wait for user to configure and connect to WiFi
                # This is a oneshot service, so we wait until connection is successful
                max_setup_time = 1800  # 30 minutes maximum setup time
                start_time = time.time()
                
                while self.running and (time.time() - start_time) < max_setup_time:
                    try:
                        # Check if we've successfully connected
                        if self.current_state == ServiceState.CONNECTED:
                            self.logger.info("WiFi connection successful - oneshot service complete")
                            # Small delay to ensure connection is stable
                            await asyncio.sleep(5)
                            return
                        
                        # Handle connection timeout
                        if (self.current_state == ServiceState.CONNECTING and 
                            self.connection_start_time and 
                            time.time() - self.connection_start_time > 120):
                            self.logger.warning("Connection timeout, returning to hotspot mode")
                            self.current_state = ServiceState.HOTSPOT_MODE
                            await self._start_hotspot_mode()
                        
                        # Check every 5 seconds
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        self.logger.error(f"Error in oneshot service loop: {e}")
                        await asyncio.sleep(5)
                
                # If we reach here, the setup time limit was exceeded
                self.logger.error(f"WiFi setup timeout after {max_setup_time} seconds")
                raise TimeoutError("WiFi setup timeout - manual intervention required")

        except Exception as e:
            self.logger.error(f"Oneshot service error: {e}")
            raise
        finally:
            await self.cleanup()

    async def _scan_networks_properly(self):
        """Scan for networks with proper hotspot handling"""
        try:
            if self.current_state == ServiceState.HOTSPOT_MODE:
                # Check if we're in the middle of a connection attempt
                if self.current_state == ServiceState.CONNECTING:
                    self.logger.info("Connection in progress, skipping network scan")
                    return []

                # Temporarily stop hotspot to get proper network scan
                self.logger.info("Temporarily stopping hotspot for network scan")
                hotspot_was_active = self.wifi_manager.is_hotspot_active()

                if hotspot_was_active:
                    await self.wifi_manager.stop_hotspot()
                    await asyncio.sleep(3)  # Wait longer for interface to be ready

                # Perform scan
                networks = await self.wifi_manager.get_available_networks()

                # Filter out our own hotspot SSID
                filtered_networks = [
                    net for net in networks if net.ssid != self.hotspot_ssid
                ]

                # Only restart hotspot if we're still in hotspot mode (not connecting)
                if (
                    hotspot_was_active
                    and self.current_state == ServiceState.HOTSPOT_MODE
                ):
                    self.logger.info("Restarting hotspot after network scan")
                    # Add delay to prevent race conditions
                    await asyncio.sleep(2)
                    await self.wifi_manager.start_hotspot(
                        self.hotspot_ssid, self.hotspot_password
                    )

                return filtered_networks
            else:
                # Normal scan when not in hotspot mode
                return await self.wifi_manager.get_available_networks()

        except Exception as e:
            self.logger.error(f"Error in network scan: {e}")
            # Try to restore hotspot if we're supposed to be in hotspot mode
            if self.current_state == ServiceState.HOTSPOT_MODE:
                try:
                    await asyncio.sleep(3)  # Prevent race conditions
                    await self.wifi_manager.start_hotspot(
                        self.hotspot_ssid, self.hotspot_password
                    )
                except Exception as restore_error:
                    self.logger.error(f"Failed to restore hotspot: {restore_error}")
            return []

    async def cleanup(self):
        """Cleanup service resources"""
        self.logger.info("Cleaning up WiFi service")

        try:
            # Stop mDNS service
            self.device_config.stop_mdns_service()
            
            # Stop hotspot if running
            if self.wifi_manager.is_hotspot_active():
                await self.wifi_manager.stop_hotspot()

        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

    async def _get_networks_without_hotspot_restart(self):
        """Get networks without stopping hotspot - use alternative method"""
        try:
            # Use a different approach that doesn't interfere with hotspot
            base_cmd = [
                "nmcli",
                "-t",
                "-f",
                "SSID,SIGNAL,SECURITY,FREQ",
                "device",
                "wifi",
                "list",
                "--rescan",
                "no",
            ]
            # Use WiFiManager's sudo handling for privileged commands
            cmd = self.wifi_manager._build_command(base_cmd)
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode != 0:
                return []

            networks = []
            seen_ssids = set()

            for line in stdout.decode().strip().split("\n"):
                if not line:
                    continue

                parts = line.split(":")
                if len(parts) >= 4:
                    ssid = parts[0]
                    signal = int(parts[1]) if parts[1].isdigit() else 0
                    security = "encrypted" if parts[2] else "open"
                    frequency = parts[3]

                    # Skip empty SSIDs, our hotspot, and duplicates
                    if ssid and ssid != self.hotspot_ssid and ssid not in seen_ssids:
                        from network.wifi_manager import NetworkInfo

                        networks.append(
                            NetworkInfo(
                                ssid=ssid,
                                signal=signal,
                                security=security,
                                frequency=frequency,
                                in_use=False,
                            )
                        )
                        seen_ssids.add(ssid)

            # Sort by signal strength
            networks.sort(key=lambda x: x.signal, reverse=True)
            # Networks found successfully
            return networks

        except Exception:
            return []


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Oneshot Distiller WiFi Service")

    parser.add_argument(
        "--ssid",
        default=None,
        help="Hotspot SSID (default: auto-generated with random suffix)",
    )
    parser.add_argument(
        "--password", default=None, help="Hotspot password (default: from device config)"
    )
    parser.add_argument(
        "--device-name",
        default=None,
        help="Device name for display (default: auto-generated with random suffix)",
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Web server port (default: 8080)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Service now runs as distiller user with proper sudo permissions

    try:
        service = DistillerWiFiService(
            hotspot_ssid=args.ssid,
            hotspot_password=args.password,
            device_name=args.device_name,
            web_port=args.port,
        )

        asyncio.run(service.run())

    except KeyboardInterrupt:
        print("\nService interrupted by user")
    except Exception as e:
        print(f"Service failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
