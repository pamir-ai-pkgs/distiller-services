"""
Pre-built screen templates for the e-ink display.

Each function returns a Layout with components configured for that screen.
No manual positioning or magic numbers needed!
"""

from .display_layouts import (
    Caption,
    Checklist,
    Component,
    Divider,
    Dots,
    Label,
    LandscapeLayout,
    LandscapeSingleColumn,
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


def format_ip_for_url(ip: str) -> str:
    """Wrap IPv6 addresses in brackets for URL compatibility."""
    return f"[{ip}]" if ":" in ip else ip


def create_setup_screen(
    ap_ssid: str,
    ap_password: str,
    mdns_hostname: str,
    ap_ip: str = "192.168.4.1",
    web_port: int = 8080,
) -> LandscapeSingleColumn:
    """
    Create WiFi setup screen with single-column layout.

    Args:
        ap_ssid: Access point SSID
        ap_password: Access point password
        mdns_hostname: mDNS hostname for web interface
        ap_ip: Access point IP address (default: 192.168.4.1)
        web_port: Web server port (default: 8080)

    Returns:
        LandscapeSingleColumn
    """
    # Generate WiFi connection string for QR code
    wifi_string = f"WIFI:T:WPA;S:{ap_ssid};P:{ap_password};;"

    layout = LandscapeSingleColumn()
    layout.add(
        Title("JOIN WIFI"),
        Space(height=theme.spacing.md),
        QRCode(wifi_string, size="medium", align="center"),
        Space(height=theme.spacing.md),
        Text(f"VISIT : {ap_ip}:{web_port}", style="label", align="center"),
    )
    return layout


def create_connecting_screen(
    ssid: str | None = None, progress: float = 0.4, status: str | None = None
) -> LandscapeLayout:
    """
    Create connecting screen with progress bar and status message.

    Args:
        ssid: Network being connected to
        progress: Connection progress (0.0 to 1.0)
        status: Connection status message (e.g., "Obtaining IP address...")

    Returns:
        LandscapeLayout
    """
    # Use provided status or default
    status_text = status or "Authenticating..."

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
            Caption(status_text),
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


def create_tunnel_screen(
    tunnel_url: str, ip_address: str, provider: str = "pinggy"
) -> LandscapeLayout:
    """
    Create tunnel/remote access screen with QR code.

    Args:
        tunnel_url: Tunnel URL (FRP or Pinggy)
        ip_address: Local IP address
        provider: Tunnel provider ("frp" or "pinggy")

    Returns:
        LandscapeLayout
    """
    # Build right side content
    formatted_ip = format_ip_for_url(ip_address) if ip_address else "0.0.0.0"
    local_url = formatted_ip

    # FRP and Pinggy have different layout requirements
    left_panel: list[Component] = [
        Title("REMOTE ACCESS"),
        Space(height=theme.spacing.sm),
        QRCode(tunnel_url, size="medium", align="center"),
        Space(height=theme.spacing.sm),
    ]

    if provider == "frp":
        right_panel: list[Component] = [
            Space(height=theme.spacing.lg),
            Space(height=theme.spacing.lg),
            Text(tunnel_url, style="value", align="center"),
            Divider("or"),
            Text(f"{local_url}/distiller/https", style="value", align="center"),
        ]
    else:  # Pinggy provider
        right_panel: list[Component] = [
            Space(height=theme.spacing.lg),
            Space(height=theme.spacing.lg),
            Text(tunnel_url, style="value", align="center"),
        ]

    return LandscapeLayout().add_left(*left_panel).add_right(*right_panel)


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
    error_title: str = "ERROR",
    error_message: str | None = None,
    retry_info: str | None = None,
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
            Text(error_message, style="body", align="center"),
            Space(height=theme.spacing.lg),
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
                (error_message if error_message else "Invalid password or network unreachable"),
                style="body",
            ),
            Space(height=theme.spacing.xxl),
            Value("Restart the board or resend credentials."),
        )
    )


def create_captive_portal_screen(device_ip: str, portal_url: str | None = None) -> LandscapeLayout:
    """
    Create captive portal authentication screen.

    Shows device IP address and QR code for user to access proxy interface.
    User connects their phone to the same WiFi network, scans QR code or
    visits the displayed URL, and completes authentication through their
    phone's browser.

    Args:
        device_ip: Device's IP address on current network
        portal_url: Detected captive portal URL (for debugging, optional)

    Returns:
        LandscapeLayout
    """
    # Generate QR code URL pointing to device's captive portal proxy
    # Format IP address (IPv6 needs brackets)
    formatted_ip = format_ip_for_url(device_ip)
    proxy_url = f"http://{formatted_ip}:8080/captive"

    return (
        LandscapeLayout()
        .add_left(
            Title("CAPTIVE PORTAL"),
            Space(height=theme.spacing.xl),
            QRCode(proxy_url, size="small"),
            Space(height=theme.spacing.md),
            Caption("Scan to authenticate"),
        )
        .add_right(
            Subtitle("1. Connect phone"),
            Subtitle("to same WiFi"),
            Space(height=theme.spacing.lg),
            Value(device_ip),
            Label(":8080/captive"),
            Space(height=theme.spacing.xl),
            Caption("2. Complete login"),
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
