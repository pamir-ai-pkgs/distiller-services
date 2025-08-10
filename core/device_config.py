"""Device configuration and identity management."""

import json
import logging
import string
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeviceIdentity(BaseModel):
    device_id: str = Field(description="Unique 4-character device identifier")
    hostname: str = Field(description="System hostname (distiller-xxxx)")
    ap_ssid: str = Field(description="Access Point SSID")
    created_at: str = Field(description="ISO timestamp of when identity was created")

    @classmethod
    def generate(cls, prefix: str = "distiller") -> "DeviceIdentity":
        import secrets
        from datetime import datetime

        # Use secrets for cryptographically secure random generation
        chars = string.ascii_lowercase + string.digits
        device_id = "".join(secrets.choice(chars) for _ in range(4))
        hostname = f"{prefix}-{device_id}"
        ap_ssid = f"Distiller-{device_id.upper()}"

        return cls(
            device_id=device_id,
            hostname=hostname,
            ap_ssid=ap_ssid,
            created_at=datetime.now().isoformat(),
        )


class DeviceConfigManager:
    def __init__(self, config_file: Path = None):
        self.config_file = config_file or Path("/var/lib/distiller/device_config.json")
        self.identity: DeviceIdentity | None = None

    def load_or_create(self) -> DeviceIdentity:
        """Load existing device identity or create a new one."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                    self.identity = DeviceIdentity(**data)
                    logger.info(f"Loaded existing device identity: {self.identity.hostname}")
                    return self.identity
            except Exception as e:
                logger.error(f"Failed to load device config: {e}")
                # Fall through to create new identity

        # Create new identity
        self.identity = DeviceIdentity.generate()
        logger.info(f"Generated new device identity: {self.identity.hostname}")

        # Save to file
        self._save_identity()

        # Configure system (hostname, /etc/hosts)
        self._configure_system()

        return self.identity

    def _save_identity(self) -> None:
        """Save device identity to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically
            temp_file = self.config_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(self.identity.model_dump(), f, indent=2)
            temp_file.rename(self.config_file)

            logger.info(f"Saved device identity to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save device identity: {e}")

    def _configure_system(self) -> None:
        """Configure system hostname and /etc/hosts."""
        if not self.identity:
            logger.error("No device identity to configure")
            return

        try:
            # Update hostname
            self._update_hostname()

            # Update /etc/hosts
            self._update_hosts_file()

            logger.info(f"System configured with hostname: {self.identity.hostname}")
        except Exception as e:
            logger.error(f"Failed to configure system: {e}")

    def _update_hostname(self) -> None:
        """Update system hostname."""
        hostname = self.identity.hostname

        try:
            # Update /etc/hostname
            with open("/etc/hostname", "w") as f:
                f.write(f"{hostname}\n")

            # Apply hostname immediately
            subprocess.run(["hostname", hostname], check=True)

            # Update using hostnamectl if available
            try:
                subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)
                logger.info(f"Updated hostname using hostnamectl: {hostname}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.info(f"Updated hostname using legacy method: {hostname}")

            # Required delay for hostname propagation (runs during init only)
            import time

            time.sleep(0.5)

            # Clear Avahi cache and restart daemon to pick up new hostname
            try:
                # Stop Avahi daemon
                subprocess.run(["systemctl", "stop", "avahi-daemon"], check=True)
                logger.info("Stopped Avahi daemon")

                # Clear Avahi cache files safely
                import shutil

                cache_dir = Path("/var/cache/avahi-daemon")
                if cache_dir.exists():
                    for item in cache_dir.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                        except Exception:
                            pass

                # Start Avahi daemon fresh
                subprocess.run(["systemctl", "start", "avahi-daemon"], check=True)
                logger.info("Started Avahi daemon with new hostname")

                # Brief delay for Avahi initialization (init only)
                time.sleep(1)

                # Verify the hostname is registered
                try:
                    result = subprocess.run(
                        ["avahi-resolve", "-n", f"{hostname}.local"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        logger.info(f"Verified mDNS hostname: {hostname}.local")
                    else:
                        logger.warning("Could not verify mDNS hostname registration")
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Failed to restart Avahi daemon - mDNS may show old hostname: {e}")

        except Exception as e:
            logger.error(f"Failed to update hostname: {e}")

    def _update_hosts_file(self) -> None:
        """Update /etc/hosts with proper entries for mDNS."""
        hostname = self.identity.hostname

        try:
            # Read existing hosts file
            with open("/etc/hosts") as f:
                lines = f.readlines()

            # Remove old distiller entries
            filtered_lines = []
            for line in lines:
                if "distiller-" not in line.lower() or line.strip().startswith("#"):
                    filtered_lines.append(line)

            # Add new entries
            new_entries = [
                "\n# Distiller CM5 Device\n",
                f"127.0.0.1\t{hostname}\n",
                f"127.0.1.1\t{hostname}.local {hostname}\n",
                f"::1\t\t{hostname}\n",
            ]

            # Find where to insert (after localhost entries)
            insert_index = 0
            for i, line in enumerate(filtered_lines):
                if "127.0.0.1" in line and "localhost" in line:
                    insert_index = i + 1
                    break

            # Insert new entries
            final_lines = (
                filtered_lines[:insert_index] + new_entries + filtered_lines[insert_index:]
            )

            # Write back atomically
            temp_file = Path("/etc/hosts.tmp")
            with open(temp_file, "w") as f:
                f.writelines(final_lines)

            # Replace original file
            temp_file.rename("/etc/hosts")

            logger.info(f"Updated /etc/hosts with entries for {hostname}")

        except Exception as e:
            logger.error(f"Failed to update /etc/hosts: {e}")

    def get_device_id(self) -> str:
        """Get the persistent device ID."""
        if not self.identity:
            self.load_or_create()
        return self.identity.device_id

    def get_hostname(self) -> str:
        """Get the system hostname."""
        if not self.identity:
            self.load_or_create()
        return self.identity.hostname

    def get_ap_ssid(self) -> str:
        """Get the AP SSID."""
        if not self.identity:
            self.load_or_create()
        return self.identity.ap_ssid

    def get_mdns_hostname(self) -> str:
        """Get the mDNS hostname (without .local)."""
        if not self.identity:
            self.load_or_create()
        return self.identity.hostname
