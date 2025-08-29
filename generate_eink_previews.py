#!/usr/bin/env python3
"""
Generate preview PNG images of all e-ink display states.
This script creates sample images showing what would appear on the 122x250 e-ink display.
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image, ImageDraw, ImageFont

from core.state import NetworkInfo, SystemState
from services.display_layouts import Caption, QRCode, Space, Text
from services.display_screens import (
    create_connected_screen,
    create_connecting_screen,
    create_custom_screen,
    create_failed_screen,
    create_initializing_screen,
    create_setup_screen,
    create_tunnel_screen,
)
from services.display_theme import theme


class MockSettings:
    """Mock settings for testing."""

    def __init__(self):
        self.device_id = "AB12"
        self.ap_ssid = "Distiller-AB12"
        self.ap_password = "setupwifi123"
        self.mdns_hostname = "distiller-ab12"
        self.display_enabled = False  # We're not using hardware
        self.display_update_interval = 2.0


class MockStateManager:
    """Mock state manager for testing."""

    def __init__(self):
        self.state = SystemState()
        self.state.network_info = NetworkInfo(
            ssid="HomeNetwork-5G",
            ip_address="192.168.1.42",
            signal_strength=-45,
            security="WPA2",
            connected_at=datetime.now(),
        )
        self.state.ap_password = "setupwifi123"
        self.state.tunnel_url = "https://rnskg-21-24-129-38.a.free.pinggy.link"

    def get_state(self):
        return self.state


def load_fonts() -> dict:
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


def generate_previews():
    """Generate all e-ink display preview images using new component system."""

    # Create mock dependencies
    settings = MockSettings()
    state_manager = MockStateManager()

    # Load fonts
    fonts = load_fonts()

    # Create output directory
    output_dir = Path("/tmp/eink_previews")
    output_dir.mkdir(exist_ok=True)

    print(f"Generating e-ink display previews in {output_dir}")
    print(f"Display size: {theme.display.width}x{theme.display.height} pixels")
    print("-" * 50)

    # Store generated images
    images = []
    titles = []

    # 1. Setup Mode - WiFi QR Code
    print("1. Generating SETUP MODE display...")
    setup_layout = create_setup_screen(
        ap_ssid=settings.ap_ssid,
        ap_password=settings.ap_password,
        mdns_hostname=settings.mdns_hostname,
    )
    setup_image = setup_layout.render(fonts)
    setup_path = output_dir / "eink_1_setup.png"
    setup_image.save(str(setup_path))
    print(f"   Saved: {setup_path}")
    print("   Shows: WiFi QR code, SSID, password, and connection instructions")
    images.append(setup_image)
    titles.append("Setup")

    # 2. Connecting - Progress animation
    print("\n2. Generating CONNECTING display...")
    connecting_layout = create_connecting_screen(ssid="HomeNetwork-5G", progress=0.4)
    connecting_image = connecting_layout.render(fonts)
    connecting_path = output_dir / "eink_2_connecting.png"
    connecting_image.save(str(connecting_path))
    print(f"   Saved: {connecting_path}")
    print("   Shows: Connection progress with dots and progress bar")
    images.append(connecting_image)
    titles.append("Connecting")

    # 3. Connected - Network info
    print("\n3. Generating CONNECTED display...")
    connected_layout = create_connected_screen(
        ssid=state_manager.state.network_info.ssid,
        ip_address=state_manager.state.network_info.ip_address,
        mdns_hostname=settings.mdns_hostname,
    )
    connected_image = connected_layout.render(fonts)
    connected_path = output_dir / "eink_3_connected.png"
    connected_image.save(str(connected_path))
    print(f"   Saved: {connected_path}")
    print("   Shows: Success checkmark, network name, IP address, signal strength")
    images.append(connected_image)
    titles.append("Connected")

    # 4. Tunnel Active - Remote access QR
    print("\n4. Generating TUNNEL ACTIVE display...")
    tunnel_layout = create_tunnel_screen(
        state_manager.state.tunnel_url, state_manager.state.network_info.ip_address
    )
    tunnel_image = tunnel_layout.render(fonts)
    tunnel_path = output_dir / "eink_4_tunnel.png"
    tunnel_image.save(str(tunnel_path))
    print(f"   Saved: {tunnel_path}")
    print("   Shows: Remote access QR code and Pinggy tunnel URL")
    images.append(tunnel_image)
    titles.append("Tunnel")

    # 5. Initializing - Boot screen
    print("\n5. Generating INITIALIZING display...")
    init_layout = create_initializing_screen()
    init_image = init_layout.render(fonts)
    init_path = output_dir / "eink_5_initializing.png"
    init_image.save(str(init_path))
    print(f"   Saved: {init_path}")
    print("   Shows: DISTILLER logo and initialization checklist")
    images.append(init_image)
    titles.append("Initializing")

    # 6. Failed - Connection failed screen
    print("\n6. Generating FAILED display...")
    failed_layout = create_failed_screen(
        ssid="BadNetwork", error_message="Invalid password or network unreachable"
    )
    failed_image = failed_layout.render(fonts)
    failed_path = output_dir / "eink_6_failed.png"
    failed_image.save(str(failed_path))
    print(f"   Saved: {failed_path}")
    print("   Shows: Connection failure message")
    images.append(failed_image)
    titles.append("Failed")

    # 7. Custom screen example
    print("\n7. Generating CUSTOM display example...")
    custom_layout = create_custom_screen(
        "CUSTOM SCREEN",
        [
            Text("This is a custom screen", style="body", align="center"),
            Space(theme.spacing.md),
            QRCode("https://example.com", size="small"),
            Space(theme.spacing.md),
            Caption("Example of custom components"),
        ],
    )
    custom_image = custom_layout.render(fonts)
    custom_path = output_dir / "eink_7_custom.png"
    custom_image.save(str(custom_path))
    print(f"   Saved: {custom_path}")
    print("   Shows: Example of custom screen composition")
    images.append(custom_image)
    titles.append("Custom")

    # Create a combined preview image showing all states
    print("\n" + "=" * 50)
    print("Creating combined preview image...")

    # Calculate dimensions for combined image
    num_images = len(images)
    cols = 4  # Display 4 images per row
    rows = (num_images + cols - 1) // cols  # Ceiling division

    combined_width = theme.display.width * cols + (cols + 1) * 10  # Add spacing
    combined_height = theme.display.height * rows + (rows + 1) * 10 + 40  # Add title space
    combined = Image.new("RGB", (combined_width, combined_height), "white")
    draw = ImageDraw.Draw(combined)

    # Try to load a font for titles
    title_font = fonts.get("medium")

    # Paste each display image
    for i, (img, title) in enumerate(zip(images, titles, strict=False)):
        col = i % cols
        row = i // cols

        x_offset = col * (theme.display.width + 10) + 10
        y_offset = row * (theme.display.height + 30) + 30

        # Draw title above image
        draw.text((x_offset, y_offset - 20), title, fill="black", font=title_font)

        # Convert monochrome to RGB and paste
        rgb_img = img.convert("RGB")
        combined.paste(rgb_img, (x_offset, y_offset))

        # Draw border around image
        draw.rectangle(
            [
                (x_offset - 1, y_offset - 1),
                (x_offset + theme.display.width, y_offset + theme.display.height),
            ],
            outline="gray",
            width=1,
        )

    combined_path = output_dir / "eink_all_states_preview.png"
    combined.save(str(combined_path))
    print(f"Combined preview saved: {combined_path}")

    print("\n" + "=" * 50)
    print("✓ All e-ink display previews generated successfully!")
    print(f"\nView the images in: {output_dir}")
    print("\nIndividual files:")
    for file in sorted(output_dir.glob("eink_*.png")):
        print(f"  - {file.name}")

    return output_dir


if __name__ == "__main__":
    try:
        output_dir = generate_previews()
        print("\nTo view the images, run:")
        print(f"  ls -la {output_dir}")
        print("  # Or open in an image viewer")
    except Exception as e:
        print(f"Error generating previews: {e}")

        traceback.print_exc()
        sys.exit(1)
