#!/usr/bin/env python3
"""
Generate preview PNG images of all e-ink display states.
This script creates sample images showing what would appear on the 128x250 e-ink display.
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image

from core.state import NetworkInfo, SystemState


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
        self.tunnel_url = "https://rnskg-21-24-129-38.a.free.pinggy.link"

    def get_state(self):
        return self.state.connection_state

    def get_current_ssid(self):
        return self.state.network_info.ssid

    def get_ip_address(self):
        return self.state.network_info.ip_address

    def get_signal_strength(self):
        return self.state.network_info.signal_strength

    def get_tunnel_url(self):
        return self.tunnel_url


def generate_previews():
    """Generate all e-ink display preview images."""

    # Import DisplayService after path is set
    from services.display_service import DisplayService

    # Create mock dependencies
    settings = MockSettings()
    state_manager = MockStateManager()

    # Initialize display service (without hardware)
    display_service = DisplayService(settings, state_manager)

    # Create output directory
    output_dir = Path("/tmp/eink_previews")
    output_dir.mkdir(exist_ok=True)

    print(f"Generating e-ink display previews in {output_dir}")
    print(f"Display size: {display_service.width}x{display_service.height} pixels")
    print("-" * 50)

    # Generate each display state

    # 1. Setup Mode - WiFi QR Code
    print("1. Generating SETUP MODE display...")
    setup_image = display_service._create_setup_image()
    setup_path = output_dir / "eink_1_setup.png"
    setup_image.save(str(setup_path))
    print(f"   Saved: {setup_path}")
    print("   Shows: WiFi QR code, SSID, password, and connection instructions")

    # 2. Connecting - Progress animation
    print("\n2. Generating CONNECTING display...")
    connecting_image = display_service._create_connecting_image()
    connecting_path = output_dir / "eink_2_connecting.png"
    connecting_image.save(str(connecting_path))
    print(f"   Saved: {connecting_path}")
    print("   Shows: Connection progress with animated circles and progress bar")

    # 3. Connected - Network info
    print("\n3. Generating CONNECTED display...")
    connected_image = display_service._create_connected_image()
    connected_path = output_dir / "eink_3_connected.png"
    connected_image.save(str(connected_path))
    print(f"   Saved: {connected_path}")
    print("   Shows: Success checkmark, network name, IP address, signal strength")

    # 4. Tunnel Active - Remote access QR
    print("\n4. Generating TUNNEL ACTIVE display...")
    tunnel_image = display_service._create_tunnel_image(state_manager.tunnel_url)
    tunnel_path = output_dir / "eink_4_tunnel.png"
    tunnel_image.save(str(tunnel_path))
    print(f"   Saved: {tunnel_path}")
    print("   Shows: Remote access QR code and Pinggy tunnel URL")

    # 5. Initializing - Boot screen
    print("\n5. Generating INITIALIZING display...")
    init_image = display_service._create_initializing_image()
    init_path = output_dir / "eink_5_initializing.png"
    init_image.save(str(init_path))
    print(f"   Saved: {init_path}")
    print("   Shows: DISTILLER CM5 logo and initialization message")

    # Create a combined preview image showing all states
    print("\n" + "=" * 50)
    print("Creating combined preview image...")

    # Create a large canvas to show all displays side by side
    combined_width = display_service.width * 5 + 40  # 5 displays + spacing
    combined_height = display_service.height + 40  # Add padding
    combined = Image.new("RGB", (combined_width, combined_height), "white")

    # Paste each display image
    images = [setup_image, connecting_image, connected_image, tunnel_image, init_image]
    titles = ["Setup", "Connecting", "Connected", "Tunnel", "Initializing"]

    for i, (img, _title) in enumerate(zip(images, titles, strict=False)):
        x_offset = i * (display_service.width + 8) + 20
        y_offset = 20

        # Convert monochrome to RGB for combined image
        rgb_img = img.convert("RGB")
        combined.paste(rgb_img, (x_offset, y_offset))

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
        import traceback

        traceback.print_exc()
        sys.exit(1)
