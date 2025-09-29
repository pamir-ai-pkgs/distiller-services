"""DNS configuration manager for connectivity check domain resolution."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DNSConfigurator:
    """Manages dnsmasq configuration for NetworkManager shared connections."""

    DNSMASQ_CONFIG_DIR = Path("/etc/NetworkManager/dnsmasq.d")
    CONFIG_FILE_NAME = "distiller-connectivity.conf"

    CONNECTIVITY_DOMAINS = [
        "connectivitycheck.gstatic.com",
        "www.google.com",
        "play.googleapis.com",
        "connectivitycheck.android.com",
        "clients3.google.com",
        "captive.apple.com",
        "www.apple.com",
        "www.msftconnect.com",
        "www.msftncsi.com",
        "detectportal.firefox.com",
    ]

    def __init__(self, ap_ip: str = "192.168.4.1"):
        self.ap_ip = ap_ip
        self.config_file_path = self.DNSMASQ_CONFIG_DIR / self.CONFIG_FILE_NAME

    def _generate_config_content(self) -> str:
        lines = [
            "# Distiller WiFi - DNS overrides for connectivity checks",
            "# Auto-managed by distiller-wifi service",
            "",
        ]
        for domain in self.CONNECTIVITY_DOMAINS:
            lines.append(f"address=/{domain}/{self.ap_ip}")
        lines.append("")
        return "\n".join(lines)

    async def setup_connectivity_dns(self) -> bool:
        """Create dnsmasq configuration before starting AP mode."""
        try:
            if not self.DNSMASQ_CONFIG_DIR.exists():
                logger.warning(f"Creating {self.DNSMASQ_CONFIG_DIR}")
                self.DNSMASQ_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            self.config_file_path.write_text(self._generate_config_content(), encoding="utf-8")
            self.config_file_path.chmod(0o644)
            logger.info(
                f"Created DNS configuration with {len(self.CONNECTIVITY_DOMAINS)} overrides"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create DNS configuration: {e}")
            return False

    async def cleanup_connectivity_dns(self) -> bool:
        """Remove dnsmasq configuration file."""
        try:
            if self.config_file_path.exists():
                self.config_file_path.unlink()
                logger.info("Removed DNS configuration")
            return True
        except Exception as e:
            logger.error(f"Failed to remove DNS configuration: {e}")
            return False

    def is_configured(self) -> bool:
        return self.config_file_path.exists()
