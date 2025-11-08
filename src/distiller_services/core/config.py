"""
Configuration management using Pydantic settings.
"""

import secrets
import string
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..paths import get_device_env_path, get_log_dir, get_state_dir
from .device_config import DeviceConfigManager


def generate_secure_password(length: int = 12) -> str:
    """Generate secure random password for AP mode."""
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


class Settings(BaseSettings):
    """Application settings with automatic validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DISTILLER_",
        case_sensitive=False,
        arbitrary_types_allowed=True,
    )

    # Device identification - will be overridden by DeviceConfigManager
    device_id: str = Field(
        default="",  # Will be set from persistent config
        description="Unique 4-character device identifier",
    )

    # Network configuration
    ap_ssid_prefix: str = Field(default="Distiller", description="Access Point SSID prefix")
    ap_password: str = Field(
        default_factory=lambda: f"setup-{generate_secure_password()}",
        description="Access Point password",
    )

    ap_ip: str = Field(default="192.168.4.1", description="Access Point IP address")
    ap_channel: int = Field(default=6, description="Access Point WiFi channel (1-11 for 2.4GHz)")
    ap_password_ttl: int = Field(
        default=1800, description="AP password time-to-live in seconds (default: 30 minutes)"
    )

    # mDNS configuration
    mdns_hostname_prefix: str = Field(default="distiller", description="mDNS hostname prefix")

    mdns_port: int = Field(default=8080, description="mDNS advertised port")

    # Web server configuration
    web_host: str = Field(
        default="0.0.0.0", description="Web server host (0.0.0.0 for IPv4 all interfaces)"
    )

    web_port: int = Field(default=8080, description="Web server port")

    # Captive portal configuration
    enable_captive_portal: bool = Field(
        default=True, description="Enable captive portal for automatic browser popup"
    )

    # Display configuration
    display_enabled: bool = Field(default=True, description="Enable e-ink display updates")

    display_update_interval: float = Field(
        default=2.0, description="Display update interval in seconds"
    )

    # Tunnel configuration
    tunnel_enabled: bool = Field(default=True, description="Enable tunnel service (FRP/Pinggy)")

    tunnel_provider: str = Field(
        default="frp", description="Primary tunnel provider (frp or pinggy)"
    )

    # FRP configuration
    devices_domain: str = Field(default="devices.pamir.ai", description="FRP devices domain")

    frp_service_name: str = Field(default="frpc.service", description="FRP systemd service name")

    device_serial: str | None = Field(default=None, description="Device serial number (override)")

    device_env_path: str = Field(
        default_factory=lambda: str(get_device_env_path()),
        description="Path to device env file",
    )

    # Pinggy configuration (backward compatibility)
    tunnel_refresh_interval: int = Field(
        default=3300, description="Tunnel refresh interval in seconds (55 minutes)"
    )

    tunnel_ssh_port: int = Field(default=443, description="SSH port for tunnel connection")

    pinggy_access_token: str | None = Field(
        default=None, description="Pinggy access token for persistent tunnels"
    )

    # Connection settings
    # Tunnel service configuration (used by TunnelService)
    tunnel_max_retries: int = Field(
        default=3, description="Maximum tunnel connection retry attempts"
    )

    tunnel_retry_delay: int = Field(
        default=30, description="Delay between tunnel retries in seconds"
    )

    # Network recovery configuration
    recovery_max_retries: int = Field(
        default=5, description="Maximum auto-recovery retry attempts after network loss"
    )

    recovery_initial_delay: float = Field(
        default=3.0, description="Initial delay before first recovery attempt (seconds)"
    )

    recovery_max_delay: float = Field(
        default=60.0, description="Maximum delay between recovery attempts (seconds)"
    )

    recovery_backoff_factor: float = Field(
        default=2.0, description="Exponential backoff multiplier for recovery delays"
    )

    # Runtime settings
    debug: bool = Field(default=False, description="Enable debug logging")

    # Paths
    state_dir: Path = Field(default_factory=get_state_dir, description="State storage directory")

    log_dir: Path = Field(default_factory=get_log_dir, description="Log file directory")

    # Device configuration manager (lazy loaded)
    _device_config: DeviceConfigManager | None = None

    def _get_device_config(self) -> DeviceConfigManager:
        """Get or create device configuration manager."""
        if self._device_config is None:
            # Use state directory for device config
            config_file = self.state_dir / "device_config.json"

            self._device_config = DeviceConfigManager(config_file=config_file)
            # Load or create identity
            identity = self._device_config.load_or_create()
            # Update our device_id
            self.device_id = identity.device_id
        return self._device_config

    @property
    def ap_ssid(self) -> str:
        """Get persistent AP SSID."""
        return self._get_device_config().get_ap_ssid()

    @property
    def mdns_hostname(self) -> str:
        """Get persistent mDNS hostname."""
        return self._get_device_config().get_mdns_hostname()

    @property
    def mdns_fqdn(self) -> str:
        """Generate fully qualified mDNS domain name."""
        return f"{self.mdns_hostname}.local"

    @property
    def state_file(self) -> Path:
        """Path to state file."""
        return self.state_dir / "state.json"

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_web_url(self, use_mdns: bool = True) -> str:
        """Get the web interface URL."""
        if use_mdns:
            return f"http://{self.mdns_fqdn}:{self.web_port}"
        return f"http://{self.ap_ip}:{self.web_port}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
