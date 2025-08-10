"""
E-ink display service for visual feedback.
"""

import asyncio
import logging
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from core.config import Settings
from core.state import ConnectionState, StateManager

logger = logging.getLogger(__name__)

# Add the SDK path to system path
SDK_PATH = Path("/opt/distiller-cm5-sdk/src")
if SDK_PATH.exists():
    sys.path.insert(0, str(SDK_PATH))


class DisplayService:
    """
    Manages e-ink display updates based on system state.

    Features:
    - QR code generation for setup URL
    - Status messages and connection info
    - Async updates without blocking
    - Graceful degradation when hardware unavailable
    - 128x250 pixel e-ink display support
    """

    def __init__(self, settings: Settings, state_manager: StateManager):
        self.settings = settings
        self.state_manager = state_manager
        self.display = None
        self._running = False

        # Display dimensions for 128x250 e-ink
        self.width = 128
        self.height = 250

        # Safe display area with margins
        self.margin = 6  # Safe margin on all sides
        self.safe_width = self.width - (2 * self.margin)  # 116px usable width
        self.content_x = self.margin  # Starting x position for content

        # Try to load fonts
        self.fonts = self._load_fonts()

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
            if width != 128 or height != 250:
                logger.warning(f"Unexpected display dimensions: {width}x{height}")

            logger.info(f"E-ink display initialized: {width}x{height}")

            # Clear display on startup
            self.display.clear()

        except ImportError as e:
            logger.warning(f"E-ink display SDK not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")

    def _load_fonts(self) -> dict:
        """Load fonts for display rendering."""
        fonts = {}

        # Try to load custom fonts, fallback to default
        # Check for MartianMono font first (custom font)
        font_paths = [
            # Production path
            "/opt/distiller-cm5-services/static/fonts/MartianMonoNerdFont-CondensedBold.ttf",
            # Development path (relative to project root)
            Path(__file__).parent.parent
            / "static"
            / "fonts"
            / "MartianMonoNerdFont-CondensedBold.ttf",
            # System fonts as fallback
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

        for path in font_paths:
            # Convert Path objects to string
            path_str = str(path) if isinstance(path, Path) else path

            if Path(path_str).exists():
                try:
                    # Optimized font sizes for 128x250 e-ink display with margins
                    fonts["large"] = ImageFont.truetype(path_str, 16)  # Headers
                    fonts["medium"] = ImageFont.truetype(path_str, 13)  # Titles
                    fonts["small"] = ImageFont.truetype(path_str, 10)  # Body text
                    fonts["tiny"] = ImageFont.truetype(path_str, 9)  # Details
                    logger.info(f"Loaded font: {path_str}")
                    break
                except Exception as e:
                    logger.debug(f"Failed to load font {path_str}: {e}")

        # Fallback to default font
        if not fonts:
            logger.warning("No custom fonts found, using default font")
            default = ImageFont.load_default()
            fonts = {
                "large": default,
                "medium": default,
                "small": default,
                "tiny": default,
            }

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
        """Update display based on current state."""
        try:
            # Get full state to check for tunnel URL
            full_state = self.state_manager.get_state()

            # Create display image based on state
            if state == ConnectionState.AP_MODE:
                image = self._create_setup_image()
            elif state == ConnectionState.CONNECTING:
                image = self._create_connecting_image()
            elif state == ConnectionState.CONNECTED:
                # Always prefer showing tunnel URL when available
                if full_state.tunnel_url:
                    image = self._create_tunnel_image(full_state.tunnel_url)
                else:
                    image = self._create_connected_image()
            else:
                image = self._create_initializing_image()

            # Send to display
            if self.display:
                await self._send_to_display(image)
            else:
                # Save to file for debugging
                debug_file = Path("/tmp/distiller_display.png")
                image.save(str(debug_file))
                logger.debug(f"Display image saved to: {debug_file}")

        except Exception as e:
            logger.error(f"Failed to update display: {e}")

    def _create_setup_image(self) -> Image.Image:
        """Create setup mode display with QR code."""
        # Create monochrome image (1-bit)
        image = Image.new("1", (self.width, self.height), 1)  # White background
        draw = ImageDraw.Draw(image)

        # Title - Centered within safe area
        title = "WIFI SETUP"
        font = self.fonts["large"]
        self._center_text(draw, title, 5, font)

        # QR Code with AP credentials - use dynamic password from state
        state = self.state_manager.get_state()
        ap_password = state.ap_password or "setupwifi123"  # Fallback to default if not set
        ap_url = f"WIFI:T:WPA;S:{self.settings.ap_ssid};P:{ap_password};;"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=3,
            border=1,
        )
        qr.add_data(ap_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        # Resize QR to fit with margins (85x85)
        qr_img = qr_img.resize((85, 85), Image.NEAREST)

        # Paste QR code centered
        qr_x = (self.width - 85) // 2
        image.paste(qr_img, (qr_x, 28))

        # Network name - Centered
        font = self.fonts["small"]
        self._center_text(draw, self.settings.ap_ssid, 120, font)

        # Password section with wrapping
        y_pos = 140
        font = self.fonts["tiny"]
        draw.text((self.content_x, y_pos), "Password:", font=font, fill=0)
        y_pos += 12

        font = self.fonts["small"]
        # Wrap password if too long
        y_pos = self._draw_wrapped_text(
            draw, ap_password, self.content_x, y_pos, font, self.safe_width
        )

        # Access URL with wrapping
        y_pos += 8
        font = self.fonts["tiny"]
        draw.text((self.content_x, y_pos), "Then open:", font=font, fill=0)
        y_pos += 12

        url = f"{self.settings.mdns_hostname}.local"
        y_pos = self._draw_wrapped_text(draw, url, self.content_x, y_pos, font, self.safe_width)

        # Scan instruction at bottom - centered and safe
        font = self.fonts["tiny"]
        scan_text = "Scan QR or connect manually"
        self._center_text(draw, scan_text, 228, font)

        return image

    def _create_connecting_image(self) -> Image.Image:
        """Create connecting mode display."""
        image = Image.new("1", (self.width, self.height), 1)
        draw = ImageDraw.Draw(image)

        # Title - Centered within safe area
        title = "CONNECTING"
        font = self.fonts["large"]
        self._center_text(draw, title, 30, font)

        # Simple animated dots
        font = self.fonts["large"]
        dots = "• • •"
        self._center_text(draw, dots, 55, font)

        # SSID being connected to - with wrapping, no defaults
        state = self.state_manager.get_state()
        ssid = state.network_info.ssid if state.network_info else None
        if ssid:
            font = self.fonts["medium"]
            self._center_text(draw, ssid, 95, font)

        # Progress bar - Centered within safe area
        bar_width = 100  # Reduced to fit safely
        bar_height = 14
        bar_x = self.margin + (self.safe_width - bar_width) // 2
        bar_y = 135

        # Outer rectangle
        draw.rectangle(
            [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], outline=0, width=2
        )
        # Fill 40% progress
        fill_width = int(bar_width * 0.4)
        draw.rectangle(
            [(bar_x + 2, bar_y + 2), (bar_x + fill_width - 2, bar_y + bar_height - 2)], fill=0
        )

        # Percentage text
        font = self.fonts["small"]
        percent = "40%"
        self._center_text(draw, percent, bar_y + bar_height + 5, font)

        # Status message
        font = self.fonts["small"]
        status = "Authenticating..."
        self._center_text(draw, status, 185, font)

        # Time estimate - with wrapping
        font = self.fonts["tiny"]
        estimate = "Usually takes 10-30 seconds"
        self._center_text(draw, estimate, 210, font)

        return image

    def _create_connected_image(self) -> Image.Image:
        """Create connected mode display."""
        image = Image.new("1", (self.width, self.height), 1)
        draw = ImageDraw.Draw(image)

        # Simple checkmark
        cx, cy = self.width // 2, 25
        draw.line([(cx - 12, cy), (cx - 4, cy + 8)], fill=0, width=3)
        draw.line([(cx - 4, cy + 8), (cx + 12, cy - 8)], fill=0, width=3)

        # Title - Centered
        title = "CONNECTED"
        font = self.fonts["large"]
        self._center_text(draw, title, 45, font)

        # Network info with safe margins
        y_pos = 75

        # SSID with wrapping - no defaults
        state = self.state_manager.get_state()
        ssid = state.network_info.ssid if state.network_info else None
        if ssid:
            font = self.fonts["tiny"]
            draw.text((self.content_x, y_pos), "Network:", font=font, fill=0)
            y_pos += 11
            font = self.fonts["small"]
            y_pos = self._draw_wrapped_text(
                draw, ssid, self.content_x, y_pos, font, self.safe_width
            )
            y_pos += 8

        # IP Address with wrapping - no defaults
        ip = self.state_manager.get_ip_address()
        if ip:
            font = self.fonts["tiny"]
            draw.text((self.content_x, y_pos), "IP Address:", font=font, fill=0)
            y_pos += 11
            font = self.fonts["small"]
            y_pos = self._draw_wrapped_text(draw, ip, self.content_x, y_pos, font, self.safe_width)
            y_pos += 8

        # Signal strength - properly wrapped
        signal = self.state_manager.get_signal_strength()
        if signal:
            font = self.fonts["tiny"]
            draw.text((self.content_x, y_pos), "Signal:", font=font, fill=0)
            y_pos += 11

            # Signal quality text - fully wrapped
            signal_text = (
                "Excellent"
                if signal >= -50
                else "Good"
                if signal >= -60
                else "Fair"
                if signal >= -70
                else "Poor"
            )
            signal_full = f"{signal_text} ({signal} dBm)"
            font = self.fonts["small"]
            y_pos = self._draw_wrapped_text(
                draw, signal_full, self.content_x, y_pos, font, self.safe_width
            )
            y_pos += 8

        # Access URL with wrapping
        font = self.fonts["tiny"]
        draw.text((self.content_x, y_pos), "Web Interface:", font=font, fill=0)
        y_pos += 11
        font = self.fonts["small"]
        url = f"{self.settings.mdns_hostname}.local:8080"
        y_pos = self._draw_wrapped_text(draw, url, self.content_x, y_pos, font, self.safe_width)

        return image

    def _create_tunnel_image(self, tunnel_url: str) -> Image.Image:
        """Create tunnel mode display with QR code."""
        image = Image.new("1", (self.width, self.height), 1)
        draw = ImageDraw.Draw(image)

        # Title - Centered
        title = "REMOTE ACCESS"
        font = self.fonts["medium"]
        self._center_text(draw, title, 5, font)

        # QR Code - Smaller to make room for text
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=2,
            border=1,
        )
        qr.add_data(tunnel_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((70, 70), Image.NEAREST)

        # Paste QR code centered
        qr_x = (self.width - 70) // 2
        image.paste(qr_img, (qr_x, 25))

        # Display FULL URL with proper wrapping
        y_pos = 105
        font = self.fonts["tiny"]
        draw.text((self.content_x, y_pos), "URL:", font=font, fill=0)
        y_pos += 12

        # Smart URL display for Pinggy
        if "pinggy" in tunnel_url:
            import re

            match = re.search(r"https?://([^/]+)", tunnel_url)
            if match:
                full_domain = match.group(1)
                parts = full_domain.split(".")

                if len(parts) >= 4:  # Pinggy format
                    # Show subdomain on its own line
                    subdomain = parts[0]
                    font = self.fonts["small"]
                    y_pos = self._draw_wrapped_text(
                        draw, subdomain, self.content_x, y_pos, font, self.safe_width
                    )

                    # Show domain suffix
                    domain_suffix = "." + ".".join(parts[1:])
                    font = self.fonts["tiny"]
                    y_pos = self._draw_wrapped_text(
                        draw, domain_suffix, self.content_x, y_pos, font, self.safe_width
                    )
                else:
                    # Show full URL with wrapping
                    font = self.fonts["tiny"]
                    y_pos = self._draw_wrapped_text(
                        draw, tunnel_url, self.content_x, y_pos, font, self.safe_width
                    )
            else:
                # Fallback - wrap full URL
                font = self.fonts["tiny"]
                y_pos = self._draw_wrapped_text(
                    draw, tunnel_url, self.content_x, y_pos, font, self.safe_width
                )
        else:
            # Non-Pinggy URL - wrap it
            font = self.fonts["tiny"]
            y_pos = self._draw_wrapped_text(
                draw, tunnel_url, self.content_x, y_pos, font, self.safe_width
            )

        # Important info - all wrapped for safety
        y_pos += 10
        font = self.fonts["small"]
        y_pos = self._draw_wrapped_text(
            draw, "Valid for: 60 minutes", self.content_x, y_pos, font, self.safe_width
        )
        y_pos += 5

        font = self.fonts["tiny"]
        y_pos = self._draw_wrapped_text(
            draw, "Access from anywhere", self.content_x, y_pos, font, self.safe_width
        )
        y_pos = self._draw_wrapped_text(
            draw, "No VPN required", self.content_x, y_pos, font, self.safe_width
        )

        # Bottom instruction - centered and safe
        font = self.fonts["tiny"]
        scan_text = "Scan QR or type URL"
        self._center_text(draw, scan_text, 228, font)

        return image

    def _create_initializing_image(self) -> Image.Image:
        """Create initializing mode display."""
        image = Image.new("1", (self.width, self.height), 1)
        draw = ImageDraw.Draw(image)

        # Logo/Title - Centered
        title = "DISTILLER"
        font = self.fonts["large"]
        self._center_text(draw, title, 40, font)

        # Subtitle
        subtitle = "CM5"
        font = self.fonts["large"]
        self._center_text(draw, subtitle, 60, font)

        # Progress dots
        font = self.fonts["medium"]
        dots = "• • • • •"
        self._center_text(draw, dots, 95, font)

        # Status message
        font = self.fonts["medium"]
        status = "STARTING UP"
        self._center_text(draw, status, 125, font)

        # Progress checklist - within safe margins
        font = self.fonts["tiny"]
        y_pos = 155
        checklist = ["✓ Hardware check", "✓ Loading services", "• Starting WiFi...", "• Ready soon"]
        for item in checklist:
            draw.text((self.content_x + 4, y_pos), item, font=font, fill=0)
            y_pos += 12

        return image

    async def _send_to_display(self, image: Image.Image):
        """Send image to e-ink display."""
        if not self.display:
            return

        try:
            # Save to temporary file
            temp_file = Path("/tmp/eink_display.png")
            image.save(str(temp_file), "PNG")

            # Display the image with full refresh for important states
            state = self.state_manager.get_state()
            if state in [ConnectionState.SETUP_MODE, ConnectionState.CONNECTED]:
                # Full refresh for important state changes
                self.display.display_image(str(temp_file), self.DisplayMode.FULL)
            else:
                # Partial refresh for progress updates
                self.display.display_image(str(temp_file), self.DisplayMode.PARTIAL)

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

    def show_message(self, message: str, duration: int = 3):
        """Show a temporary message on the display."""
        if not self.display:
            return

        try:
            image = Image.new("1", (self.width, self.height), 1)
            draw = ImageDraw.Draw(image)

            # Wrap and display message
            font = self.fonts["small"]
            lines = self._wrap_text(message, font, self.width - 20)

            y_pos = (self.height - len(lines) * 12) // 2
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                draw.text(((self.width - line_width) // 2, y_pos), line, font=font, fill=0)
                y_pos += 12

            # Send to display
            temp_file = Path("/tmp/eink_message.png")
            image.save(str(temp_file), "PNG")
            self.display.display_image(str(temp_file), self.DisplayMode.PARTIAL)

        except Exception as e:
            logger.error(f"Failed to show message: {e}")

    def _wrap_text(self, text: str, font, max_width: int) -> list:
        """Wrap text to fit within max_width, breaking at word boundaries."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                # Check if single word is too long
                if font.getbbox(word)[2] - font.getbbox(word)[0] > max_width:
                    # Break long word
                    while (
                        len(word) > 0 and font.getbbox(word)[2] - font.getbbox(word)[0] > max_width
                    ):
                        for i in range(len(word), 0, -1):
                            if font.getbbox(word[:i])[2] - font.getbbox(word[:i])[0] <= max_width:
                                lines.append(word[:i])
                                word = word[i:]
                                break
                    if word:
                        current_line = [word]
                    else:
                        current_line = []

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def _draw_wrapped_text(
        self, draw, text: str, x: int, y: int, font, max_width: int, fill=0, line_spacing=2
    ) -> int:
        """Draw wrapped text and return the final y position."""
        lines = self._wrap_text(text, font, max_width)
        line_height = font.size + line_spacing

        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height

        return y

    def _center_text(self, draw, text: str, y: int, font, fill=0, line_spacing=2):
        """Center text within safe display area, wrapping if needed."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

        # If text is too wide, wrap it
        if text_width > self.safe_width:
            lines = self._wrap_text(text, font, self.safe_width)
            line_height = font.size + line_spacing
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                x = self.margin + (self.safe_width - line_width) // 2
                draw.text((x, y), line, font=font, fill=fill)
                y += line_height
            return y
        else:
            x = self.margin + (self.safe_width - text_width) // 2
            draw.text((x, y), text, font=font, fill=fill)
            return y + font.size + line_spacing
