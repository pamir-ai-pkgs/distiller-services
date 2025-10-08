"""
E-ink display service for visual feedback.
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageFont

from core.config import Settings
from core.state import ConnectionState, StateManager

from .display_screens import (
    create_connected_screen,
    create_connecting_screen,
    create_failed_screen,
    create_initializing_screen,
    create_setup_screen,
    create_tunnel_screen,
)

logger = logging.getLogger(__name__)

# Add the SDK path to system path
SDK_PATH = Path("/opt/distiller-sdk/src")
if SDK_PATH.exists():
    sys.path.insert(0, str(SDK_PATH))

# Try to import TemplateRenderer for custom UI templates
try:
    from distiller_sdk.hardware.eink.composer import TemplateRenderer

    TEMPLATE_RENDERER_AVAILABLE = True
except ImportError:
    logger.debug("TemplateRenderer not available, will use hardcoded screens only")
    TEMPLATE_RENDERER_AVAILABLE = False


class DisplayService:
    """
    Manages e-ink display updates based on system state.

    Features:
    - Component-based layouts with no magic numbers
    - QR code generation for setup URL
    - Status messages and connection info
    - Async updates without blocking
    - Graceful degradation when hardware unavailable
    - 128x250 pixel e-ink display support
    """

    def __init__(self, settings: Settings, state_manager: StateManager):
        self.settings = settings
        self.state_manager = state_manager
        self.display: Any = None
        self._running = False
        self._display_lock = asyncio.Lock()

        # Template path for UI-generated templates
        self.template_path = Path("/home/distiller/template/default/template.json")

        # Load fonts
        self.fonts = self.load_fonts()

        # Initialize hardware if display is enabled
        if settings.display_enabled:
            self._init_hardware()

        # Register for state changes
        self.state_manager.on_state_change(self._on_state_change)

    def _init_hardware(self):
        """Initialize e-ink display but don't hold it."""
        try:
            # Import the actual SDK
            from distiller_sdk.hardware.eink.display import (
                Display,
                DisplayMode,
                DitheringMethod,
                ScalingMethod,
            )

            # Create display object without auto-initialization
            self.display = Display(auto_init=False)
            self.DisplayMode = DisplayMode
            self.ScalingMethod = ScalingMethod
            self.DitheringMethod = DitheringMethod

            # Initialize the display
            assert self.display is not None
            self.display.initialize()
            width, height = self.display.get_dimensions()
            logger.info(f"E-ink display ready: {width}x{height}")

            # Clear display on startup
            self.display.clear()

        except ImportError as e:
            logger.warning(f"E-ink display SDK not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")

    def load_fonts(self) -> dict[str, ImageFont.FreeTypeFont]:
        """Load fonts for rendering."""
        fonts = {}

        # Use MartianMono font from static/fonts (parent directory)
        font_path = (
            Path(__file__).parent.parent
            / "static"
            / "fonts"
            / "MartianMonoNerdFont-CondensedBold.ttf"
        )

        try:
            # Load font at different sizes
            fonts["large"] = ImageFont.truetype(str(font_path), 14)
            fonts["medium"] = ImageFont.truetype(str(font_path), 12)
            fonts["small"] = ImageFont.truetype(str(font_path), 11)
            fonts["xs"] = ImageFont.truetype(str(font_path), 10)

            print(f"Loaded font: {font_path}")

        except Exception as e:
            print(f"Failed to load font: {e}")
            raise RuntimeError(f"Required font not found at {font_path}") from None

        return fonts

    def _has_template(self) -> bool:
        """Check if a custom UI template exists."""
        if not TEMPLATE_RENDERER_AVAILABLE:
            return False
        return self.template_path.exists()

    def _render_template(self, ip_address: str, tunnel_url: str) -> Image.Image | None:
        """
        Render custom UI template with dynamic data.

        Args:
            ip_address: Current IP address
            tunnel_url: Tunnel URL for QR code

        Returns:
            PIL Image of rendered template or None on failure
        """
        if not TEMPLATE_RENDERER_AVAILABLE or not self._has_template():
            return None

        try:
            # Create renderer with template
            renderer = TemplateRenderer(str(self.template_path))

            # Create temporary file for rendered output
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Render and save to temporary file
            renderer.render_and_save(ip_address, tunnel_url, temp_path)

            # Load as PIL Image
            image = Image.open(temp_path)

            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

            logger.debug(f"Successfully rendered template with IP: {ip_address}, URL: {tunnel_url}")
            return image

        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return None

    async def run(self):
        """Display service keepalive loop."""
        self._running = True

        logger.info("Display service started")

        while self._running:
            try:
                # NOTE: All display updates are handled via the _on_state_change callback.
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Display service error: {e}")
                await asyncio.sleep(5)

    async def update_display(self, state):
        """Update display based on current state using new component system."""
        async with self._display_lock:
            try:
                # Always get fresh state to ensure we have latest tunnel_url
                full_state = self.state_manager.get_state()
                # Use fresh state for screen decision instead of stale parameter
                current_state = full_state.connection_state
                image = None

                # Try to use custom template for connected state with tunnel URL
                if (
                    current_state == ConnectionState.CONNECTED
                    and full_state.tunnel_url
                    and self._has_template()
                ):
                    # Get IP address for template rendering
                    ip_address = "127.0.0.1"
                    if full_state.network_info and full_state.network_info.ip_address:
                        ip_address = full_state.network_info.ip_address

                    # Try to render custom template
                    image = self._render_template(ip_address, full_state.tunnel_url)

                    if image:
                        logger.info("Using custom UI template for display")

                # If no custom template or rendering failed, use hardcoded screens
                if not image:
                    # Create appropriate screen based on fresh state
                    if current_state == ConnectionState.AP_MODE:
                        # Setup screen with WiFi credentials
                        ap_password = full_state.ap_password or "setupwifi123"
                        layout = create_setup_screen(
                            ap_ssid=self.settings.ap_ssid,
                            ap_password=ap_password,
                            mdns_hostname=self.settings.mdns_hostname,
                            ap_ip=self.settings.ap_ip,
                            web_port=self.settings.web_port,
                        )

                    elif current_state == ConnectionState.CONNECTING:
                        # Connecting screen with progress
                        ssid = full_state.network_info.ssid if full_state.network_info else None
                        layout = create_connecting_screen(ssid=ssid, progress=0.4)

                    elif current_state == ConnectionState.CONNECTED:
                        # Check if we have a tunnel URL to show
                        if full_state.tunnel_url:
                            provider = full_state.tunnel_provider or "pinggy"
                            layout = create_tunnel_screen(
                                full_state.tunnel_url,
                                full_state.network_info.ip_address,
                                provider=provider,
                            )
                        else:
                            # Regular connected screen
                            network_info = full_state.network_info
                            layout = create_connected_screen(
                                ssid=network_info.ssid if network_info else None,
                                ip_address=network_info.ip_address if network_info else None,
                                mdns_hostname=self.settings.mdns_hostname,
                            )

                    elif current_state == ConnectionState.FAILED:
                        # Connection failed screen
                        network_info = full_state.network_info
                        layout = create_failed_screen(
                            ssid=network_info.ssid if network_info else None,
                            error_message=full_state.error_message,
                        )

                    else:
                        # Default initializing screen
                        layout = create_initializing_screen()

                    # Render the layout to an image
                    image = layout.render(self.fonts)

                # Send to display
                if self.display:
                    # Image is from template if it was rendered by _render_template
                    is_from_template = (
                        TEMPLATE_RENDERER_AVAILABLE
                        and self._has_template()
                        and image is not None
                        and current_state == ConnectionState.CONNECTED
                        and full_state.tunnel_url
                    )
                    await self._send_to_display(image, current_state, is_template=is_from_template)
                else:
                    # Save to file for debugging
                    debug_file = Path("/tmp/distiller_display.png")
                    image.save(str(debug_file))
                    logger.debug(f"Display image saved to: {debug_file}")

            except Exception as e:
                logger.error(f"Failed to update display: {e}", exc_info=True)

    async def _on_state_change(self, old_state, new_state):
        """Handle state changes via callback to force immediate display update."""
        logger.info(f"State change callback: {old_state} -> {new_state}")
        await self.update_display(new_state)

    async def _send_to_display(self, image, state, is_template=False):
        """Send image to e-ink display with conditional rotation for templates."""
        if not self.display:
            return

        try:
            # Ensure display is initialized (re-initialize if closed)
            if not self.display.is_initialized():
                self.display.initialize()
                width, height = self.display.get_dimensions()
                logger.debug(f"Re-initialized display: {width}x{height}")

            temp_file = Path("/tmp/eink_display.png")
            image.save(str(temp_file), "PNG")

            # Display png image
            self.display.display_png_auto(
                str(temp_file),
                mode=self.DisplayMode.FULL,
                rotate=90 if is_template else 180,
                flop=False,
                flip=True,
            )

            logger.debug(f"Display updated for state: {state}")
            await asyncio.sleep(2)  # Give time for the display to refresh
            self.display.sleep()  # Put display to sleep after update
            self.display.close()  # Close connection

        except Exception as e:
            logger.error(f"Failed to send image to display: {e}")

    async def stop(self):
        """Stop the display service."""
        self._running = False

        # Clear and close display on shutdown
        if self.display:
            try:
                self.display.clear()
                self.display.sleep()
                self.display.close()
            except Exception as e:
                logger.error(f"Error during display shutdown: {e}")

        logger.info("Display service stopped")
