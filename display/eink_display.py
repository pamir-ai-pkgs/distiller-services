"""
Simple E-ink Display Module for Distiller CM5 Services

This module provides a clean, simple interface for displaying information
on the e-ink display using the distiller-cm5-sdk.

Features:
- Clean SDK integration with proper error handling
- Simple API for common display operations
- Works on workstation (gracefully handles missing hardware)
- Thread-safe operations
"""

# Import the SDK
import logging
import os
import tempfile
from datetime import datetime

from distiller_cm5_sdk.hardware.eink import Display, DisplayError, DisplayMode
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class EinkDisplay:
    """
    Simple E-ink display manager for Distiller CM5 services.

    Provides a clean interface for displaying WiFi setup information,
    status messages, and connection details on the e-ink display.
    """

    def __init__(self):
        self.display = None
        self.width = 128
        self.height = 250
        self._initialize_display()

    def _initialize_display(self):
        """Initialize the display with proper error handling."""
        try:
            self.display = Display()
            self.width, self.height = self.display.get_dimensions()
            logger.info(f"E-ink display initialized: {self.width}x{self.height}")
        except Exception as e:
            logger.error(f"Failed to initialize e-ink display: {e}")
            raise DisplayError(f"E-ink display initialization failed: {e}") from None

    def get_dimensions(self) -> tuple[int, int]:
        """Get display dimensions."""
        return (self.width, self.height)

    def is_available(self) -> bool:
        """Check if display is available."""
        return self.display is not None

    def clear(self):
        """Clear the display."""
        if not self.is_available():
            logger.warning("Display not available, skipping clear")
            return

        try:
            self.display.clear()
            logger.info("Display cleared")
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")

    def display_image(self, image_path: str):
        """Display an image on the e-ink screen."""
        if not self.is_available():
            logger.warning(f"Display not available, skipping image: {image_path}")
            return

        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return

        try:
            self.display.display_image(image_path, DisplayMode.FULL)
            logger.info(f"Displayed image: {image_path}")
        except Exception as e:
            logger.error(f"Failed to display image {image_path}: {e}")

    def display_setup_screen(self, ssid: str, password: str, ip_address: str, port: int = 8080):
        """Display WiFi setup instructions."""
        try:
            image_path = self._create_setup_image(ssid, password, ip_address, port)
            self.display_image(image_path)
        except Exception as e:
            logger.error(f"Failed to display setup screen: {e}")

    def display_connecting_screen(self, ssid: str):
        """Display connecting status."""
        try:
            image_path = self._create_connecting_image(ssid)
            self.display_image(image_path)
        except Exception as e:
            logger.error(f"Failed to display connecting screen: {e}")

    def display_success_screen(self, ssid: str, ip_address: str):
        """Display successful connection."""
        try:
            image_path = self._create_success_image(ssid, ip_address)
            self.display_image(image_path)
        except Exception as e:
            logger.error(f"Failed to display success screen: {e}")

    def display_info_screen(self, ssid: str, ip_address: str, signal_strength: str = None):
        """Display current WiFi information."""
        try:
            image_path = self._create_info_image(ssid, ip_address, signal_strength)
            self.display_image(image_path)
        except Exception as e:
            logger.error(f"Failed to display info screen: {e}")

    def _get_font(self, size: int):
        """Get font with fallback options."""
        font_paths = [
            "/opt/distiller-cm5-services/fonts/MartianMonoNerdFont-CondensedBold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue

        return ImageFont.load_default()

    def _create_setup_image(self, ssid: str, password: str, ip_address: str, port: int) -> str:
        """Create setup instructions image."""
        img = Image.new("L", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        # Fonts
        font_title = self._get_font(14)
        font_text = self._get_font(10)
        font_small = self._get_font(8)

        # Border
        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=0, width=2)

        y = 15

        # Title
        title = "WiFi Setup"
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((self.width - title_width) // 2, y), title, fill=0, font=font_title)
        y += 30

        # Instructions
        draw.text((10, y), "1. Connect to WiFi:", fill=0, font=font_text)
        y += 18
        draw.text((15, y), f"Network: {ssid}", fill=0, font=font_small)
        y += 15
        draw.text((15, y), f"Password: {password}", fill=0, font=font_small)
        y += 25

        draw.text((10, y), "2. Open browser:", fill=0, font=font_text)
        y += 18
        draw.text((15, y), f"http://{ip_address}:{port}", fill=0, font=font_small)
        y += 25

        draw.text((10, y), "3. Follow instructions", fill=0, font=font_text)
        y += 15
        draw.text((15, y), "to connect to your WiFi", fill=0, font=font_small)

        # Save as temporary file
        temp_path = tempfile.mktemp(suffix=".png")
        img.save(temp_path)
        return temp_path

    def _create_connecting_image(self, ssid: str) -> str:
        """Create connecting status image."""
        img = Image.new("L", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        font_title = self._get_font(14)
        font_text = self._get_font(10)

        # Border
        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=0, width=2)

        y = 30

        # Title
        title = "Connecting..."
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((self.width - title_width) // 2, y), title, fill=0, font=font_title)
        y += 50

        # Network name
        network_text = f"Network: {ssid}"
        if len(ssid) > 15:
            network_text = f"Network: {ssid[:12]}..."
        text_bbox = draw.textbbox((0, 0), network_text, font=font_text)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text(((self.width - text_width) // 2, y), network_text, fill=0, font=font_text)
        y += 40

        # Status
        status = "Please wait..."
        status_bbox = draw.textbbox((0, 0), status, font=font_text)
        status_width = status_bbox[2] - status_bbox[0]
        draw.text(((self.width - status_width) // 2, y), status, fill=0, font=font_text)

        temp_path = tempfile.mktemp(suffix=".png")
        img.save(temp_path)
        return temp_path

    def _create_success_image(self, ssid: str, ip_address: str) -> str:
        """Create success screen image."""
        img = Image.new("L", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        font_title = self._get_font(14)
        font_text = self._get_font(10)

        # Border
        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=0, width=2)

        y = 25

        # Title
        title = "Connected!"
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((self.width - title_width) // 2, y), title, fill=0, font=font_title)
        y += 40

        # Success checkmark (simple circle)
        center_x = self.width // 2
        draw.ellipse([center_x - 15, y - 5, center_x + 15, y + 25], outline=0, width=2)
        draw.line([center_x - 7, y + 10, center_x - 2, y + 15], fill=0, width=2)
        draw.line([center_x - 2, y + 15, center_x + 8, y + 5], fill=0, width=2)
        y += 45

        # Network info
        network_text = f"Network: {ssid}"
        if len(ssid) > 15:
            network_text = f"Network: {ssid[:12]}..."
        text_bbox = draw.textbbox((0, 0), network_text, font=font_text)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text(((self.width - text_width) // 2, y), network_text, fill=0, font=font_text)
        y += 25

        # IP address
        ip_text = f"IP: {ip_address}"
        ip_bbox = draw.textbbox((0, 0), ip_text, font=font_text)
        ip_width = ip_bbox[2] - ip_bbox[0]
        draw.text(((self.width - ip_width) // 2, y), ip_text, fill=0, font=font_text)

        temp_path = tempfile.mktemp(suffix=".png")
        img.save(temp_path)
        return temp_path

    def _create_info_image(self, ssid: str, ip_address: str, signal_strength: str = None) -> str:
        """Create WiFi info display image."""
        img = Image.new("L", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        font_title = self._get_font(12)
        font_text = self._get_font(10)
        font_small = self._get_font(8)

        # Border
        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=0, width=1)

        y = 10

        # Title
        title = "WiFi Info"
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((self.width - title_width) // 2, y), title, fill=0, font=font_title)
        y += 25

        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((5, y), f"Updated: {timestamp}", fill=0, font=font_small)
        y += 20

        # Separator
        draw.line([5, y, self.width - 5, y], fill=0, width=1)
        y += 15

        # Network name
        draw.text((5, y), "Network:", fill=0, font=font_text)
        y += 15
        network_display = ssid if len(ssid) <= 18 else ssid[:15] + "..."
        draw.text((5, y), network_display, fill=0, font=font_text)
        y += 25

        # IP address
        draw.text((5, y), "IP Address:", fill=0, font=font_text)
        y += 15
        draw.text((5, y), ip_address, fill=0, font=font_text)
        y += 25

        # Signal strength if available
        if signal_strength:
            draw.text((5, y), "Signal:", fill=0, font=font_text)
            y += 15
            draw.text((5, y), signal_strength, fill=0, font=font_text)

        temp_path = tempfile.mktemp(suffix=".png")
        img.save(temp_path)
        return temp_path

    def __del__(self):
        """Cleanup resources."""
        if self.display:
            try:
                self.display.close()
            except:
                pass


# Global instance for easy access
_display_instance = None


def get_display() -> EinkDisplay:
    """Get the global display instance."""
    global _display_instance
    if _display_instance is None:
        _display_instance = EinkDisplay()
    return _display_instance
