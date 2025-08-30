"""
Pre-built screen templates for the e-ink display.

Each function returns a Layout with components configured for that screen.
No manual positioning or magic numbers needed!
"""

from .display_layouts import (
    Caption,
    Checklist,
    Dots,
    Label,
    LandscapeLayout,
    Layout,
    ProgressBar,
    QRCode,
    Space,
    Subtitle,
    Text,
    Title,
    Value,
)
from .display_theme import theme


def create_setup_screen(
    ap_ssid: str,
    ap_password: str,
    mdns_hostname: str,
    ap_ip: str = "192.168.4.1",
    web_port: int = 8080,
) -> LandscapeLayout:
    """
    Create WiFi setup screen with dual QR codes optimized for small display.

    Args:
        ap_ssid: Access point SSID
        ap_password: Access point password
        mdns_hostname: mDNS hostname for web interface
        ap_ip: Access point IP address (default: 192.168.4.1)
        web_port: Web server port (default: 8080)

    Returns:
        LandscapeLayout
    """
    # Generate WiFi connection string for QR code
    wifi_string = f"WIFI:T:WPA;S:{ap_ssid};P:{ap_password};;"
    
    # Generate web URL for second QR code (using IP since we're in AP mode)
    web_url = f"http://{mdns_hostname}.local:{web_port}"

    return (
        LandscapeLayout()
        .add_left(
            Caption("1. Join Wifi"),
            QRCode(wifi_string, size="small"),
            Caption(ap_ssid),
            Caption(ap_password),
        )
        .add_right(
            Caption("2. Open this site"),
            QRCode(web_url, size="small"),
            Caption(ap_ip),
            Caption(f":{web_port}"),
        )
    )


def create_connecting_screen(ssid: str | None = None, progress: float = 0.4) -> LandscapeLayout:
    """
    Create connecting screen with progress bar.

    Args:
        ssid: Network being connected to
        progress: Connection progress (0.0 to 1.0)

    Returns:
        LandscapeLayout
    """
    return (
        LandscapeLayout()
        .add_left(
            Title("CONNECTING TO"),
            Space(height=theme.spacing.xxl),
            Space(height=theme.spacing.xxl),
            Space(),
            Value(ssid if ssid else "Unknown"),
            Space(),
            Dots(count=4),
        )
        .add_right(
            Caption("Takes 10-30 seconds"),
            Space(height=theme.spacing.xxl),
            ProgressBar(progress, show_percentage=True),
            Space(height=theme.spacing.xxl),
            Space(height=theme.spacing.xxl),
            Space(height=theme.spacing.xxl),
            Caption("Authenticating..."),
        )
    )


def create_connected_screen(
    ssid: str | None = None,
    ip_address: str | None = None,
    mdns_hostname: str = "distiller",
) -> LandscapeLayout:
    """
    Create connected screen showing network info.

    Args:
        ssid: Connected network name
        ip_address: Device IP address
        mdns_hostname: mDNS hostname for web interface

    Returns:
        LandscapeLayout
    """
    return (
        LandscapeLayout()
        .add_left(
            Title("CONNECTED TO"),
            Space(height=theme.spacing.xxl),
            Space(height=theme.spacing.xxl),
            Space(),
            Value(ssid if ssid else "Unknown"),
            ProgressBar(0.8, show_percentage=True),
        )
        .add_right(
            Label("IP Address:"),
            Value(ip_address if ip_address else "Unknown"),
            Space(height=theme.spacing.xxl),
            Space(height=theme.spacing.xxl),
            Label("Web Interface:"),
            Value(f"http://{mdns_hostname}.local:8080"),
        )
    )


def create_tunnel_screen(tunnel_url: str, ip_address: str) -> LandscapeLayout:
    """
    Create tunnel/remote access screen with QR code.

    Args:
        tunnel_url: Pinggy tunnel URL

    Returns:
        LandscapeLayout
    """
    return (
        LandscapeLayout()
        .add_left(
            Title("REMOTE ACCESS"),
            Space(),
            QRCode(tunnel_url, size="small"),
        )
        .add_right(
            # Label("URL:"),
            # Value(tunnel_url),
            Space(height=theme.spacing.md),
            Space(height=theme.spacing.md),
            Space(height=theme.spacing.md),
            Value("QR valid only"),
            Label("55 minutes"),
            Space(),  # Push to bottom
            Value(f"or visit"),
            Label(f"{ip_address}  :3000"),
        )
    )


def create_initializing_screen() -> LandscapeLayout:
    """
    Create initializing/startup screen.

    Returns:
        LandscapeLayout
    """
    return (
        LandscapeLayout()
        .add_left(
            Title("DISTILLER"),
            Space(),
            Dots(count=4),
            Space(),
            Subtitle("STARTING UP"),
            Space(),
            ProgressBar(0.2, show_percentage=True),
        )
        .add_right(
            Space(),
            Checklist(
                [
                    ("Hardware check", True),
                    ("Loading services", True),
                    ("Starting WiFi...", False),
                    ("Ready soon", False),
                ],
                spacing=theme.spacing.xxl,
            ),
        )
    )


def create_error_screen(
    error_title: str = "ERROR", error_message: str | None = None, retry_info: str | None = None
) -> Layout:
    """
    Create error screen.

    Args:
        error_title: Error title
        error_message: Error description
        retry_info: Retry information

    Returns:
        Layout with error screen components
    """
    layout = Layout().add(Title(error_title), Space(height=theme.spacing.lg))

    if error_message:
        layout.add(
            Text(error_message, style="body", align="center"), Space(height=theme.spacing.lg)
        )

    if retry_info:
        layout.add(Caption(retry_info))

    return layout


def create_failed_screen(
    ssid: str | None = None, error_message: str | None = None
) -> LandscapeLayout:
    """
    Create connection failed screen.

    Args:
        ssid: Network that failed to connect
        error_message: Failure reason

    Returns:
        LandscapeLayout
    """
    # Use "X" character for failure symbol
    return (
        LandscapeLayout()
        .add_left(
            Title("CONNECTION"),
            Title("FAILED:"),
            Space(height=theme.spacing.xxl),
            Title(ssid if ssid else "Unknown"),
        )
        .add_right(
            Text(
                error_message if error_message else "Invalid password or network unreachable",
                style="body",
            ),
            Space(height=theme.spacing.xxl),
            Value("Check credentials and try again."),
        )
    )


def create_custom_screen(title: str, components: list) -> Layout:
    """
    Create a custom screen with provided components.

    Args:
        title: Screen title
        components: List of components to add

    Returns:
        Layout with custom components

    Example:
        screen = create_custom_screen(
            "MY SCREEN",
            [
                Text("Hello World"),
                Space(),
                QRCode("https://example.com"),
                Caption("Custom screen example")
            ]
        )
    """
    layout = Layout().add(Title(title))

    if components:
        layout.add(Space(height=theme.spacing.lg))
        for component in components:
            layout.add(component)

    return layout
