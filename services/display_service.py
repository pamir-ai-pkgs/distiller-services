"""
E-ink display service for visual feedback.
"""

import asyncio
import logging
import sys
from pathlib import Path

from PIL import ImageFont

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
SDK_PATH = Path("/opt/distiller-cm5-sdk/src")
if SDK_PATH.exists():
    sys.path.insert(0, str(SDK_PATH))


class DisplayService:
    """
    Manages e-ink display updates based on system state.

    Features:
    - Component-based layouts with no magic numbers
    - QR code generation for setup URL
    - Status messages and connection info
    - Async updates without blocking
    - Graceful degradation when hardware unavailable
    - 122x250 pixel e-ink display support
    """

    def __init__(self, settings: Settings, state_manager: StateManager):
        self.settings = settings
        self.state_manager = state_manager
        self.display = None
        self._running = False

        # Load fonts
        self.fonts = self.load_fonts()

        # Initialize hardware if display is enabled
        if settings.display_enabled:
            self._init_hardware()

    def _init_hardware(self):
        """Initialize e-ink display hardware."""
        try:
            # Import the actual SDK
            from distiller_cm5_sdk.hardware.eink.display import Display, DisplayMode

            self.display = Display(auto_init=True)
            self.DisplayMode = DisplayMode

            # Verify display dimensions
            width, height = self.display.get_dimensions()
            if width != 122 or height != 250:
                logger.warning(f"Unexpected display dimensions: {width}x{height}")

            logger.info(f"E-ink display initialized: {width}x{height}")

            # Clear display on startup
            self.display.clear()

        except ImportError as e:
            logger.warning(f"E-ink display SDK not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")

    def load_fonts(self) -> dict[str, ImageFont.FreeTypeFont]:
        """Load fonts for rendering."""
        fonts = {}

        # Use MartianMono font from static/fonts
        font_path = Path(__file__).parent / "static" / "fonts" / "MartianMonoNerdFont-CondensedBold.ttf"

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

    async def run(self):
        """Main display update loop."""
        self._running = True
        last_state = None
        last_tunnel_url = None

        logger.info("Display service started")

        while self._running:
            try:
                # Get current state
                current_state = self.state_manager.get_state()

                # Update display if state changed or tunnel URL changed
                state_changed = last_state != current_state.connection_state
                tunnel_changed = last_tunnel_url != current_state.tunnel_url

                if state_changed or tunnel_changed:
                    await self.update_display(current_state.connection_state)
                    last_state = current_state.connection_state
                    last_tunnel_url = current_state.tunnel_url

                # Wait before next update
                await asyncio.sleep(self.settings.display_update_interval)

            except Exception as e:
                logger.error(f"Display update error: {e}")
                await asyncio.sleep(5)

    async def update_display(self, state):
        """Update display based on current state using new component system."""
        try:
            # Get full state for additional info
            full_state = self.state_manager.get_state()

            # Create appropriate screen based on state
            if state == ConnectionState.AP_MODE:
                # Setup screen with WiFi credentials
                ap_password = full_state.ap_password or "setupwifi123"
                layout = create_setup_screen(
                    ap_ssid=self.settings.ap_ssid,
                    ap_password=ap_password,
                    mdns_hostname=self.settings.mdns_hostname,
                )

            elif state == ConnectionState.CONNECTING:
                # Connecting screen with progress
                ssid = full_state.network_info.ssid if full_state.network_info else None
                layout = create_connecting_screen(ssid=ssid, progress=0.4)

            elif state == ConnectionState.CONNECTED:
                # Check if we have a tunnel URL to show
                if full_state.tunnel_url:
                    layout = create_tunnel_screen(full_state.tunnel_url)
                else:
                    # Regular connected screen
                    network_info = full_state.network_info
                    layout = create_connected_screen(
                        ssid=network_info.ssid if network_info else None,
                        ip_address=network_info.ip_address if network_info else None,
                        mdns_hostname=self.settings.mdns_hostname,
                    )

            elif state == ConnectionState.FAILED:
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
                await self._send_to_display(image, state)
            else:
                # Save to file for debugging
                debug_file = Path("/tmp/distiller_display.png")
                image.save(str(debug_file))
                logger.debug(f"Display image saved to: {debug_file}")

        except Exception as e:
            logger.error(f"Failed to update display: {e}")

    async def _send_to_display(self, image, state):
        """Send image to e-ink display."""
        if not self.display:
            return

        try:
            # Save to temporary file
            temp_file = Path("/tmp/eink_display.png")
            image.save(str(temp_file), "PNG")

            # Display the image with full refresh for important states
            if state in [ConnectionState.AP_MODE, ConnectionState.CONNECTED]:
                # Full refresh for important state changes
                self.display.display_image_auto(
                    str(temp_file), self.DisplayMode.FULL, rotate=1, flop=1
                )
            else:
                # Partial refresh for progress updates
                self.display.display_image_auto(
                    str(temp_file), self.DisplayMode.PARTIAL, rotate=1, flop=1
                )

            logger.debug(f"Display updated for state: {state}")

        except Exception as e:
            logger.error(f"Failed to send image to display: {e}")

    async def stop(self):
        """Stop the display service."""
        self._running = False

        # Clear display on shutdown
        if self.display:
            try:
                self.display.clear()
                self.display.sleep()
            except:
                pass

        logger.info("Display service stopped")
