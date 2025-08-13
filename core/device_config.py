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
    def __init__(self, config_file: Path | None = None):
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
                if not self.identity:
                    raise ValueError("No device identity to save")
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
        if not self.identity:
            logger.error("No device identity to update hostname")
            return
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
        import os
        import shutil
        import tempfile

        if not self.identity:
            logger.error("No device identity to update /etc/hosts")
            return
        hostname = self.identity.hostname

        try:
            # Read existing hosts file
            with open("/etc/hosts") as f:
                lines = f.readlines()

            # Update or add the 127.0.1.1 entry
            updated_lines = []
            found_127_0_1_1 = False

            for line in lines:
                # Skip old Distiller comment headers
                if line.strip() == "# Distiller CM5 Device":
                    continue

                # Update 127.0.1.1 line if it exists
                if line.strip().startswith("127.0.1.1"):
                    updated_lines.append(f"127.0.1.1\t{hostname}\n")
                    found_127_0_1_1 = True
                else:
                    updated_lines.append(line)

            # If 127.0.1.1 wasn't found, add it after localhost
            if not found_127_0_1_1:
                insert_index = 0
                for i, line in enumerate(updated_lines):
                    if "127.0.0.1" in line and "localhost" in line:
                        insert_index = i + 1
                        break
                updated_lines.insert(insert_index, f"127.0.1.1\t{hostname}\n")

            # Write to temp file first
            temp_fd, temp_path = tempfile.mkstemp(dir="/tmp", prefix="hosts.")
            try:
                with os.fdopen(temp_fd, "w") as f:
                    f.writelines(updated_lines)

                # Set proper permissions
                os.chmod(temp_path, 0o644)

                # Try atomic replace first (works on same filesystem)
                try:
                    os.replace(temp_path, "/etc/hosts")
                    logger.info(f"Updated /etc/hosts with entry for {hostname} (atomic)")
                except OSError as e:
                    # If atomic replace fails (cross-filesystem or busy), use copy
                    if e.errno == 16 or e.errno == 18:  # EBUSY or EXDEV (cross-device link)
                        logger.debug(f"Atomic replace failed ({e}), using copy method")
                        # Create backup first
                        backup_path = "/etc/hosts.bak"
                        shutil.copy2("/etc/hosts", backup_path)
                        try:
                            # Copy temp file content to /etc/hosts
                            shutil.copy2(temp_path, "/etc/hosts")
                            logger.info(f"Updated /etc/hosts with entry for {hostname} (copy)")
                        except Exception:
                            # Restore backup on failure
                            shutil.copy2(backup_path, "/etc/hosts")
                            raise
                    else:
                        raise

            finally:
                # Always clean up temp file
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Failed to update /etc/hosts: {e}")

    def get_device_id(self) -> str:
        """Get the persistent device ID."""
        if not self.identity:
            self.load_or_create()
        return self.identity.device_id  # pyright: ignore[reportOptionalMemberAccess]

    def get_hostname(self) -> str:
        """Get the system hostname."""
        if not self.identity:
            self.load_or_create()
        return self.identity.hostname  # pyright: ignore[reportOptionalMemberAccess]

    def get_ap_ssid(self) -> str:
        """Get the AP SSID."""
        if not self.identity:
            self.load_or_create()
        return self.identity.ap_ssid  # pyright: ignore[reportOptionalMemberAccess]

    def get_mdns_hostname(self) -> str:
        """Get the mDNS hostname (without .local)."""
        if not self.identity:
            self.load_or_create()
        return self.identity.hostname  # pyright: ignore[reportOptionalMemberAccess]
