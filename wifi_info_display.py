"""
WiFi Information Display for E-Ink
Generates and displays WiFi network information on e-ink display

Uses distiller-cm5-sdk for e-ink display operations:
- Display resolution: 128x250 pixels (configurable via SDK)
- Uses distiller_cm5_sdk.hardware.eink for all display operations
- Requires distiller-cm5-sdk to be installed and available
- Optimized fonts and layout for e-ink displays

The distiller-cm5-sdk provides clean API and hardware abstraction.
"""

import sys
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# QR code generation
try:
    import qrcode
except ImportError:
    qrcode = None
    logging.warning(
        "qrcode package not available. Install with: pip install qrcode[pil]"
    )

# Add the distiller project path to import NetworkUtils
from network.network_utils import NetworkUtils

# Import the distiller-cm5-sdk e-ink display functions
try:
    from distiller_cm5_sdk.hardware.eink import (
        Display,
        DisplayMode,
        DisplayError,
        display_png,
        clear_display,
        get_display_info
    )
    logger.info("distiller-cm5-sdk loaded successfully")
except ImportError as e:
    logger.error(f"Failed to import distiller-cm5-sdk: {e}")
    logger.error("Please ensure distiller-cm5-sdk is installed and available")
    sys.exit(1)


def get_eink_display_dimensions():
    """
    Get e-ink display dimensions from distiller-cm5-sdk
    
    Returns:
        Tuple of (width, height) in pixels
    """
    try:
        from distiller_cm5_sdk.hardware.eink import Display
        display = Display(auto_init=False)
        width, height = display.get_dimensions()
        logger.debug(f"Got display dimensions from SDK: {width}x{height}")
        return width, height
    except Exception as e:
        logger.warning(f"Could not get display dimensions from SDK: {e}")
        logger.warning("Falling back to default 128x250 dimensions")
        return 128, 250


def create_wifi_info_image(
    filename="wifi_info.png", auto_display=False, tunnel_url=None
):
    """
    Create an image with WiFi information for e-ink display

    Args:
        filename: Output filename
        auto_display: If True, automatically display on e-ink after creating
        tunnel_url: Optional tunnel URL to display with QR code

    Returns:
        Filename of created image
    """
    # Get dynamic display dimensions from SDK
    width, height = get_eink_display_dimensions()
    logger.info(f"Using display dimensions: {width}x{height}")

    # Get network information
    logger.info("Gathering network information...")
    network_utils = NetworkUtils()

    # Collect all network data
    wifi_name = network_utils.get_wifi_name()
    ip_address = network_utils.get_wifi_ip_address()
    # mac_address = network_utils.get_wifi_mac_address()
    signal_strength = network_utils.get_wifi_signal_strength()
    # network_details = network_utils.get_network_details()

    logger.info(f"WiFi: {wifi_name}, IP: {ip_address}")

    # Create image
    img = Image.new("L", (width, height), 255)  # White background
    draw = ImageDraw.Draw(img)

    # Try to load fonts - prioritize MartianMono (optimized for eink display)
    try:
        # Use MartianMono font from local directory
        martian_font_path = (
            "/opt/distiller-cm5-services/fonts/MartianMonoNerdFont-CondensedBold.ttf"
        )
        font_title = ImageFont.truetype(martian_font_path, 14)
        font_large = ImageFont.truetype(martian_font_path, 12)
        font_medium = ImageFont.truetype(martian_font_path, 10)
        font_small = ImageFont.truetype(martian_font_path, 9)
        font_tiny = ImageFont.truetype(martian_font_path, 8)
        logger.info("Using MartianMono font for better readability")
    except Exception as e:
        logger.warning(f"Could not load MartianMono font: {e}")
        try:
            # Fallback to Liberation fonts with smaller sizes
            font_title = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 13
            )
            font_large = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 11
            )
            font_medium = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 10
            )
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 9
            )
            font_tiny = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 8
            )
        except:
            try:
                # Fallback fonts with smaller sizes
                font_title = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 13)
                font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 11)
                font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 10)
                font_small = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 9)
                font_tiny = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 8)
            except:
                # Use default font
                font_title = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_tiny = ImageFont.load_default()

    # Border
    draw.rectangle([0, 0, width - 1, height - 1], outline=0, width=1)

    y_pos = 8

    # Title with WiFi icon (simple representation)
    title = "WIFI INFO"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]

    # Check if title still overflows and use smaller font if needed
    if title_width > (width - 40):  # Leave space for WiFi icon and margins
        bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = bbox[2] - bbox[0]
        draw.text(((width - title_width) // 2, y_pos), title, fill=0, font=font_large)
    else:
        draw.text(((width - title_width) // 2, y_pos), title, fill=0, font=font_title)

    # Draw simple WiFi icon (smaller for smaller display)
    icon_x = (width - title_width) // 2 - 18
    icon_y = y_pos + 3
    # Simple WiFi symbol using arcs
    for i in range(3):
        radius = 4 + i * 2
        draw.arc(
            [icon_x - radius, icon_y - radius, icon_x + radius, icon_y + radius],
            start=225,
            end=315,
            fill=0,
            width=1,
        )
    draw.ellipse([icon_x - 1, icon_y - 1, icon_x + 1, icon_y + 1], fill=0)

    y_pos += 20

    # Timestamp with timezone
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    if (
        not timestamp.endswith(" Z") and not timestamp.split()[-1]
    ):  # If no timezone info
        import time

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" {time.tzname[0]}"

    draw.text((5, y_pos), f"Updated: {timestamp}", fill=0, font=font_tiny)
    y_pos += 15

    # Horizontal separator
    draw.line([5, y_pos, width - 5, y_pos], fill=0, width=1)
    y_pos += 10

    # WiFi Network Name (SSID)
    draw.text((5, y_pos), "NETWORK NAME:", fill=0, font=font_medium)
    y_pos += 12

    # Display SSID with larger font, handle long names for smaller display
    ssid_display = wifi_name if len(wifi_name) <= 14 else wifi_name[:11] + "..."
    draw.text((5, y_pos), ssid_display, fill=0, font=font_large)
    y_pos += 18

    # IP Address
    draw.text((5, y_pos), "IP ADDRESS:", fill=0, font=font_medium)
    y_pos += 12
    draw.text((5, y_pos), ip_address, fill=0, font=font_large)
    y_pos += 18

    # If tunnel URL is provided, show compact layout with QR code
    if tunnel_url:
        # Horizontal separator
        draw.line([5, y_pos, width - 5, y_pos], fill=0, width=1)
        y_pos += 8

        # Terminal Access title
        draw.text((5, y_pos), "TERMINAL ACCESS:", fill=0, font=font_medium)
        y_pos += 15

        # Generate QR code if qrcode is available
        if qrcode:
            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=2,
                    border=1,
                )
                qr.add_data(tunnel_url)
                qr.make(fit=True)

                # Create QR code image
                qr_img = qr.make_image(fill_color="black", back_color="white")

                # Resize to fit (target size: 80x80)
                qr_size = 80
                qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

                # Center the QR code
                qr_x = (width - qr_size) // 2
                qr_y = y_pos

                # Convert to grayscale and paste
                qr_img = qr_img.convert("L")
                img.paste(qr_img, (qr_x, qr_y))

                y_pos = qr_y + qr_size + 5

                # URL text (break into lines)
                # Remove https:// prefix for space
                display_url = tunnel_url.replace("https://", "")
                if len(display_url) > 20:
                    # Split at the dot before "free"
                    parts = display_url.split(".free")
                    if len(parts) == 2:
                        draw.text((5, y_pos), parts[0], fill=0, font=font_tiny)
                        y_pos += 10
                        draw.text(
                            (5, y_pos), ".free" + parts[1], fill=0, font=font_tiny
                        )
                    else:
                        draw.text(
                            (5, y_pos), display_url[:20] + "...", fill=0, font=font_tiny
                        )
                else:
                    draw.text((5, y_pos), display_url, fill=0, font=font_tiny)
                y_pos += 12

                # Port info
                draw.text((5, y_pos), "Port: 3000", fill=0, font=font_small)

            except Exception as e:
                logger.error(f"Error generating QR code: {e}")
                # Fallback: just show URL
                draw.text((5, y_pos), "Tunnel URL:", fill=0, font=font_small)
                y_pos += 12
                draw.text((5, y_pos), tunnel_url[:25] + "...", fill=0, font=font_tiny)
        else:
            # No QR code library, just show URL
            draw.text((5, y_pos), "Tunnel URL:", fill=0, font=font_small)
            y_pos += 12
            draw.text((5, y_pos), tunnel_url[:25] + "...", fill=0, font=font_tiny)
    else:
        # Original layout when no tunnel URL
        # Signal Strength with visual indicator
        draw.text((5, y_pos), "SIGNAL STRENGTH:", fill=0, font=font_medium)
        y_pos += 12
        draw.text((5, y_pos), signal_strength or "Unknown", fill=0, font=font_large)

        # Draw signal strength bars (smaller for smaller display)
        signal_x = 5
        signal_y = y_pos + 15

        # Extract percentage from signal strength if available
        signal_percent = 0
        if signal_strength and "%" in signal_strength:
            try:
                signal_percent = int(signal_strength.split("%")[0])
            except:
                signal_percent = 50  # Default
        else:
            signal_percent = 50  # Default if no percentage

        # Draw 5 signal bars (smaller)
        for i in range(5):
            bar_height = 3 + i * 2
            bar_x = signal_x + i * 8
            bar_y = signal_y + (10 - bar_height)

            # Fill bar if signal is strong enough
            if signal_percent > (i * 20):
                draw.rectangle([bar_x, bar_y, bar_x + 6, signal_y + 10], fill=0)
            else:
                draw.rectangle(
                    [bar_x, bar_y, bar_x + 6, signal_y + 10], outline=0, width=1
                )

        y_pos += 30

        # SSH Connection Instructions
        draw.text((5, y_pos), "SSH CONNECTION:", fill=0, font=font_medium)
        y_pos += 12
        ssh_command = f"distiller@{ip_address}"
        draw.text((5, y_pos), ssh_command, fill=0, font=font_small)
        y_pos += 18

        # Default Password
        draw.text((5, y_pos), "PASSWORD:", fill=0, font=font_medium)
        y_pos += 12
        draw.text((5, y_pos), "one", fill=0, font=font_large)
        y_pos += 18

    # MAC Address
    # draw.text((10, y_pos), "MAC ADDRESS:", fill=0, font=font_medium)
    # y_pos += 20

    # # Split MAC address into two lines if too long
    # if len(mac_address) > 17:
    #     mac_line1 = mac_address[:17]
    #     mac_line2 = mac_address[17:]
    #     draw.text((10, y_pos), mac_line1, fill=0, font=font_small)
    #     y_pos += 15
    #     draw.text((10, y_pos), mac_line2, fill=0, font=font_small)
    #     y_pos += 20
    # else:
    #     draw.text((10, y_pos), mac_address, fill=0, font=font_small)
    #     y_pos += 25

    # # Hostname
    # hostname = network_details.get("hostname", "Unknown")
    # draw.text((10, y_pos), "HOSTNAME:", fill=0, font=font_medium)
    # y_pos += 20
    # draw.text((10, y_pos), hostname, fill=0, font=font_small)
    # y_pos += 25

    # Network Interfaces
    # interfaces = network_details.get("interfaces", [])
    # if interfaces:
    #     draw.text((10, y_pos), "NETWORK INTERFACES:", fill=0, font=font_medium)
    #     y_pos += 20

    #     for interface in interfaces[:3]:  # Show up to 3 interfaces
    #         if_name = interface.get("name", "unknown")
    #         if_type = interface.get("type", "unknown")
    #         if_ip = interface.get("ip_address", "no IP")

    #         # Truncate long interface names
    #         if len(if_name) > 12:
    #             if_name = if_name[:9] + "..."

    #         interface_text = f"{if_name} ({if_type})"
    #         draw.text((10, y_pos), interface_text, fill=0, font=font_tiny)
    #         y_pos += 12

    #         if if_ip != "no IP":
    #             draw.text((15, y_pos), f"IP: {if_ip}", fill=0, font=font_tiny)
    #             y_pos += 12
    #         y_pos += 5

    # QR Code placeholder (simple box with QR text)
    # qr_y = height - 80
    # qr_size = 60
    # qr_x = width - qr_size - 10

    # Draw QR code placeholder
    # draw.rectangle([qr_x, qr_y, qr_x + qr_size, qr_y + qr_size], outline=0, width=2)

    # Simple QR pattern (decorative)
    # for i in range(5, qr_size-5, 8):
    #     for j in range(5, qr_size-5, 8):
    #         if (i + j) % 16 == 0:
    #             draw.rectangle([qr_x + i, qr_y + j, qr_x + i + 6, qr_y + j + 6], fill=0)

    # QR label
    # draw.text((qr_x, qr_y + qr_size + 5), "Connect", fill=0, font=font_tiny)
    # draw.text((qr_x + 5, qr_y + qr_size + 15), "Info", fill=0, font=font_tiny)

    # Footer
    # footer_y = height - 15
    # footer_text = "Network Status Display"
    # bbox = draw.textbbox((0, 0), footer_text, font=font_tiny)
    # footer_width = bbox[2] - bbox[0]
    # draw.text(((width - footer_width) // 2, footer_y), footer_text, fill=0, font=font_tiny)

    # Save the image
    img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img.save(filename)
    logger.info(f"WiFi info image saved as: {filename}")

    # Auto-display if requested
    if auto_display:
        display_on_eink(filename)

    return filename


def display_on_eink(image_path):
    """Display the image on the e-ink screen using distiller-cm5-sdk"""
    logger.info("Displaying image on e-ink screen...")

    try:
        # Use the distiller-cm5-sdk convenience function
        display_png(image_path, DisplayMode.FULL)
        logger.info("WiFi info displayed successfully on e-ink using distiller-cm5-sdk")
        return True

    except DisplayError as e:
        logger.error(f"Display error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error displaying on e-ink: {e}")
        return False


def create_wifi_setup_image(
    ssid,
    password,
    ip_address,
    port=8080,
    filename="wifi_setup.png",
    auto_display=False,
):
    """
    Create an image with WiFi setup instructions including QR code

    Args:
        ssid: WiFi network name
        password: WiFi password
        ip_address: IP address for the web interface
        port: Port number for the web interface
        filename: Output filename
        auto_display: If True, automatically display on e-ink after creating

    Returns:
        Filename of created image
    """
    # Get dynamic display dimensions from SDK
    width, height = get_eink_display_dimensions()
    logger.info(f"Using display dimensions: {width}x{height}")

    # Create image
    img = Image.new("L", (width, height), 255)  # White background
    draw = ImageDraw.Draw(img)

    # Try to load fonts (optimized for eink display)
    try:
        martian_font_path = (
            "/opt/distiller-cm5-services/fonts/MartianMonoNerdFont-CondensedBold.ttf"
        )
        font_title = ImageFont.truetype(martian_font_path, 13)
        # font_large = ImageFont.truetype(martian_font_path, 11)
        font_medium = ImageFont.truetype(martian_font_path, 9)
        font_small = ImageFont.truetype(martian_font_path, 8)
        font_tiny = ImageFont.truetype(
            martian_font_path, 7
        )  # For long text that might overflow
        logger.info("Using MartianMono font for setup instructions")
    except Exception as e:
        logger.warning(f"Could not load MartianMono font: {e}")
        try:
            font_title = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 12
            )
            font_large = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 10
            )
            font_medium = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 9
            )
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 8
            )
            font_tiny = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 7
            )
        except:
            font_title = ImageFont.load_default()
            # font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_tiny = ImageFont.load_default()

    # Border
    draw.rectangle([0, 0, width - 1, height - 1], outline=0, width=2)

    y_pos = 15

    # Title
    title = "WIFI SETUP"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]
    draw.text(((width - title_width) // 2, y_pos), title, fill=0, font=font_title)
    y_pos += 35

    # Setup icon (simple WiFi + gear)
    icon_x = (width - title_width) // 2 - 35
    icon_y = y_pos - 25
    # WiFi symbol
    for i in range(3):
        radius = 6 + i * 3
        draw.arc(
            [icon_x - radius, icon_y - radius, icon_x + radius, icon_y + radius],
            start=225,
            end=315,
            fill=0,
            width=2,
        )
    draw.ellipse([icon_x - 2, icon_y - 2, icon_x + 2, icon_y + 2], fill=0)
    # Gear symbol
    gear_x = icon_x + 25
    draw.ellipse([gear_x - 6, icon_y - 6, gear_x + 6, icon_y + 6], outline=0, width=2)
    draw.ellipse([gear_x - 3, icon_y - 3, gear_x + 3, icon_y + 3], fill=0)

    # Instructions
    draw.text((10, y_pos), "CONNECT TO WIFI:", fill=0, font=font_medium)
    y_pos += 20

    # Network name - truncate if too long
    network_text = f"Network: {ssid}"
    if len(network_text) > 25:  # Adjust based on your display width
        network_text = f"Network: {ssid[:18]}..."
    draw.text((10, y_pos), network_text, fill=0, font=font_medium)
    y_pos += 22

    # Password - use smaller font and possibly split if very long
    password_text = f"Password: {password}"
    if len(password_text) > 30:
        # Split into two lines if password is very long
        draw.text((10, y_pos), "Password:", fill=0, font=font_medium)
        y_pos += 15
        draw.text((10, y_pos), password, fill=0, font=font_tiny)
        y_pos += 20
    else:
        draw.text((10, y_pos), password_text, fill=0, font=font_small)
        y_pos += 25

    # Separator line
    draw.line([10, y_pos, width - 10, y_pos], fill=0, width=1)
    y_pos += 15

    # Web interface instructions
    draw.text((10, y_pos), "OPEN WEB BROWSER:", fill=0, font=font_medium)
    y_pos += 20

    # URL - use smaller font for better fit and possibly split long URLs
    url = f"http://{ip_address}:{port}"
    if len(url) > 25:
        # Split URL if too long
        draw.text((10, y_pos), f"http://{ip_address}", fill=0, font=font_small)
        y_pos += 16
        draw.text((10, y_pos), f":{port}", fill=0, font=font_small)
        y_pos += 20
    else:
        draw.text((10, y_pos), url, fill=0, font=font_small)
        y_pos += 25

    # QR Code section
    if qrcode:
        try:
            # Generate QR code with higher resolution
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=4,  # Increased from 2 to 4 for better resolution
                border=1,
            )
            qr.add_data(url)
            qr.make(fit=True)

            # Create QR code image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img = qr_img.convert("L")  # Convert to grayscale

            # Resize QR code to fit - make it larger
            qr_size = min(
                width - 10, height - y_pos - 20
            )  # Reduced margins for more space
            qr_size = min(qr_size, 150)  # Increased max size from 120 to 150
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

            # Position QR code
            qr_x = (width - qr_size) // 2
            qr_y = y_pos + 10

            # Paste QR code
            img.paste(qr_img, (qr_x, qr_y))

            # QR code label
            y_pos = qr_y + qr_size + 10
            # label = "Scan QR code or type URL above"
            # bbox = draw.textbbox((0, 0), label, font=font_small)
            # label_width = bbox[2] - bbox[0]
            # draw.text(
            #     ((width - label_width) // 2, y_pos), label, fill=0, font=font_small
            # )

        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}")
            # Fallback: just show text instructions
            draw.text((10, y_pos), "Type the URL above", fill=0, font=font_medium)
            draw.text((10, y_pos + 15), "in your browser", fill=0, font=font_medium)
    else:
        # No QR code available
        draw.text((10, y_pos), "Type the URL above", fill=0, font=font_medium)
        draw.text((10, y_pos + 15), "in your browser", fill=0, font=font_medium)

    # Footer
    # footer_y = height - 15
    # footer_text = "Configure WiFi Settings"
    # bbox = draw.textbbox((0, 0), footer_text, font=font_small)
    # footer_width = bbox[2] - bbox[0]
    # draw.text(
    #     ((width - footer_width) // 2, footer_y), footer_text, fill=0, font=font_small
    # )

    # Save the image
    img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img.save(filename)
    logger.info(f"WiFi setup image saved as: {filename}")

    # Auto-display if requested
    if auto_display:
        display_on_eink(filename)

    return filename


def create_wifi_success_image(
    ssid,
    ip_address,
    filename="wifi_success.png",
    auto_display=False,
):
    """
    Create an image showing successful WiFi connection

    Args:
        ssid: Connected WiFi network name
        ip_address: Assigned IP address
        filename: Output filename
        auto_display: If True, automatically display on e-ink after creating

    Returns:
        Filename of created image
    """
    # Get dynamic display dimensions from SDK
    width, height = get_eink_display_dimensions()
    logger.info(f"Using display dimensions: {width}x{height}")

    # Create image
    img = Image.new("L", (width, height), 255)  # White background
    draw = ImageDraw.Draw(img)

    # Try to load fonts (optimized for eink display)
    try:
        martian_font_path = (
            "/opt/distiller-cm5-services/fonts/MartianMonoNerdFont-CondensedBold.ttf"
        )
        font_title = ImageFont.truetype(martian_font_path, 14)
        font_large = ImageFont.truetype(martian_font_path, 11)
        font_medium = ImageFont.truetype(martian_font_path, 9)
        font_small = ImageFont.truetype(martian_font_path, 8)
        logger.info("Using MartianMono font for success screen")
    except Exception as e:
        logger.warning(f"Could not load MartianMono font: {e}")
        try:
            font_title = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 13
            )
            font_large = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 11
            )
            font_medium = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 9
            )
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 8
            )
        except:
            font_title = ImageFont.load_default()
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Border
    draw.rectangle([0, 0, width - 1, height - 1], outline=0, width=2)

    y_pos = 20

    # Success title
    title = "WIFI CONNECTED!"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]
    draw.text(((width - title_width) // 2, y_pos), title, fill=0, font=font_title)
    y_pos += 40

    # Success checkmark (simple)
    check_x = (width - title_width) // 2 - 30
    check_y = y_pos - 30
    # Draw checkmark
    draw.ellipse(
        [check_x - 15, check_y - 15, check_x + 15, check_y + 15], outline=0, width=3
    )
    # Checkmark inside circle
    draw.line([check_x - 7, check_y, check_x - 2, check_y + 5], fill=0, width=3)
    draw.line([check_x - 2, check_y + 5, check_x + 8, check_y - 5], fill=0, width=3)

    # Connected network
    draw.text((10, y_pos), "CONNECTED TO:", fill=0, font=font_medium)
    y_pos += 20

    # Network name
    network_text = ssid
    if len(network_text) > 20:
        network_text = ssid[:17] + "..."
    draw.text((10, y_pos), network_text, fill=0, font=font_large)
    y_pos += 35

    # IP Address
    draw.text((10, y_pos), "IP ADDRESS:", fill=0, font=font_medium)
    y_pos += 20
    draw.text((10, y_pos), ip_address, fill=0, font=font_large)
    y_pos += 40

    # Separator line
    draw.line([10, y_pos, width - 10, y_pos], fill=0, width=1)
    y_pos += 20

    # Success message
    success_msg = "Setup Complete!"
    bbox = draw.textbbox((0, 0), success_msg, font=font_large)
    msg_width = bbox[2] - bbox[0]
    draw.text(((width - msg_width) // 2, y_pos), success_msg, fill=0, font=font_large)
    y_pos += 30

    # Instructions
    instructions = [
        "Your device is now connected",
        "to the WiFi network.",
        "",
        "You can close the setup",
        "browser window.",
    ]

    for instruction in instructions:
        if instruction:  # Skip empty lines
            bbox = draw.textbbox((0, 0), instruction, font=font_small)
            inst_width = bbox[2] - bbox[0]
            draw.text(
                ((width - inst_width) // 2, y_pos), instruction, fill=0, font=font_small
            )
        y_pos += 16

    # Footer
    footer_y = height - 15
    footer_text = "WiFi Setup Complete"
    bbox = draw.textbbox((0, 0), footer_text, font=font_small)
    footer_width = bbox[2] - bbox[0]
    draw.text(
        ((width - footer_width) // 2, footer_y), footer_text, fill=0, font=font_small
    )

    # Save the image
    img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img.save(filename)
    logger.info(f"WiFi success image saved as: {filename}")

    # Auto-display if requested
    if auto_display:
        display_on_eink(filename)

    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Display WiFi information on e-ink screen"
    )
    parser.add_argument(
        "--output", type=str, default="wifi_info.png", help="Output image filename"
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Automatically display on e-ink after creating",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Only display on e-ink, do not save image file",
    )
    # Removed hardcoded width/height arguments - now uses SDK dimensions
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Create setup screen instead of info screen",
    )
    parser.add_argument("--ssid", type=str, help="WiFi SSID for setup screen")
    parser.add_argument("--password", type=str, help="WiFi password for setup screen")
    parser.add_argument("--ip", type=str, help="IP address for setup screen")
    parser.add_argument("--success", action="store_true", help="Create success screen")
    parser.add_argument(
        "--connected-ip", type=str, help="Connected IP address for success screen"
    )

    args = parser.parse_args()

    try:
        if args.setup:
            if not args.ssid or not args.password or not args.ip:
                print("Setup mode requires --ssid, --password, and --ip arguments")
                return 1

            if args.no_image:
                temp_filename = "/tmp/wifi_setup_temp.png"
                create_wifi_setup_image(
                    args.ssid,
                    args.password,
                    args.ip,
                    filename=temp_filename,
                    auto_display=True,
                )
                try:
                    os.remove(temp_filename)
                except:
                    pass
            else:
                filename = create_wifi_setup_image(
                    args.ssid,
                    args.password,
                    args.ip,
                    filename=args.output,
                    auto_display=args.display,
                )
                print(f"WiFi setup image created: {filename}")

        elif args.success:
            if not args.ssid or not args.connected_ip:
                print("Success mode requires --ssid and --connected-ip arguments")
                return 1

            if args.no_image:
                temp_filename = "/tmp/wifi_success_temp.png"
                create_wifi_success_image(
                    args.ssid,
                    args.connected_ip,
                    filename=temp_filename,
                    auto_display=True,
                )
                try:
                    os.remove(temp_filename)
                except:
                    pass
            else:
                filename = create_wifi_success_image(
                    args.ssid,
                    args.connected_ip,
                    filename=args.output,
                    auto_display=args.display,
                )
                print(f"WiFi success image created: {filename}")

        elif args.no_image:
            # Create temporary image and display directly
            temp_filename = "/tmp/wifi_info_temp.png"
            create_wifi_info_image(temp_filename, auto_display=True)
            # Clean up temp file
            try:
                os.remove(temp_filename)
            except:
                pass
        else:
            # Create image file
            filename = create_wifi_info_image(args.output, auto_display=args.display)

            print(f"WiFi information image created: {filename}")

            if not args.display:
                print(f"To display on e-ink: .venv/bin/python wifi_info_display.py --display")

        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
