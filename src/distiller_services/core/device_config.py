"""Device configuration and identity management."""

import datetime
import json
import logging
import os
import re
import secrets
import shutil
import stat
import string
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from ..paths import get_state_dir

logger = logging.getLogger(__name__)


class DeviceIdentity(BaseModel):
    device_id: str = Field(description="Unique 4-character device identifier")
    hostname: str = Field(description="System hostname (distiller-xxxx)")
    ap_ssid: str = Field(description="Access Point SSID")
    created_at: str = Field(description="ISO timestamp of when identity was created")

    @classmethod
    def generate(cls, prefix: str = "distiller") -> "DeviceIdentity":
        """Generate device identity using MAC address if possible, fallback to random."""
        # Try MAC-based generation first
        try:
            return cls.generate_from_mac(prefix=prefix)
        except Exception as e:
            logger.warning(f"MAC-based generation failed, using random: {e}")

        # Fallback to random generation
        # Validate prefix to prevent hostname injection
        if not re.match(r"^[a-z][a-z0-9-]{0,15}$", prefix):
            logger.error(f"Invalid prefix for hostname: {prefix}")
            prefix = "distiller"  # Use safe default

        # Use secrets for cryptographically secure random generation
        chars = string.ascii_lowercase + string.digits
        device_id = "".join(secrets.choice(chars) for _ in range(4))

        # Validate generated hostname (max 63 chars, alphanumeric and hyphens only)
        hostname = f"{prefix}-{device_id}"
        if len(hostname) > 63:
            hostname = hostname[:63]

        # Additional hostname validation
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", hostname):
            logger.error(f"Generated hostname failed validation: {hostname}")
            # Fallback to safe hostname
            hostname = f"distiller-{device_id}"

        ap_ssid = f"Distiller-{device_id.upper()}"

        return cls(
            device_id=device_id,
            hostname=hostname,
            ap_ssid=ap_ssid,
            created_at=datetime.datetime.now().isoformat(),
        )

    @classmethod
    def generate_from_mac(
        cls, mac_address: str | None = None, prefix: str = "distiller"
    ) -> "DeviceIdentity":
        """Generate device identity from MAC address.

        Args:
            mac_address: MAC address string (e.g., "aa:bb:cc:dd:ee:ff") or None to auto-detect
            prefix: Hostname prefix (default: "distiller")

        Returns:
            DeviceIdentity with MAC-based device_id

        Raises:
            ValueError: If MAC address cannot be detected or is invalid
        """
        # Validate prefix to prevent hostname injection
        if not re.match(r"^[a-z][a-z0-9-]{0,15}$", prefix):
            logger.error(f"Invalid prefix for hostname: {prefix}")
            prefix = "distiller"  # Use safe default

        if mac_address is None:
            # Try network interface method first (more reliable)
            mac_address = cls._get_primary_mac()
            if mac_address is None:
                # Fall back to uuid.getnode() if interface method fails
                mac_address = cls._get_mac_from_uuid()
                if mac_address is None:
                    raise ValueError("Could not detect MAC address")

        # Clean up MAC address (remove colons, convert to lowercase)
        clean_mac = mac_address.lower().replace(":", "").replace("-", "")

        # Validate MAC address format
        if not re.match(r"^[0-9a-f]{12}$", clean_mac):
            raise ValueError(f"Invalid MAC address format: {mac_address}")

        # Use last 4 hex characters for device ID (converted to alphanumeric)
        # This provides 65,536 unique combinations
        mac_suffix = clean_mac[-4:]

        # Ensure device_id is alphanumeric (some systems don't handle pure hex well in hostnames)
        # Convert hex to a mix of letters and numbers for better compatibility
        device_id = ""
        for char in mac_suffix:
            # Map hex chars to alphanumeric (0-9 -> 0-9, a-f -> a-f)
            device_id += char

        hostname = f"{prefix}-{device_id}"
        ap_ssid = f"Distiller-{device_id.upper()}"

        logger.info(f"Generated MAC-based identity: {hostname} from MAC {mac_address}")

        return cls(
            device_id=device_id,
            hostname=hostname,
            ap_ssid=ap_ssid,
            created_at=datetime.datetime.now().isoformat(),
        )

    @staticmethod
    def _get_mac_from_uuid() -> str | None:
        """Get MAC address using uuid.getnode() for consistency."""
        try:
            import uuid

            mac_num = uuid.getnode()
            # Check if it's a real MAC (uuid.getnode() is deterministic)
            # If it's not a real MAC, it would be random each time
            mac_num2 = uuid.getnode()
            if mac_num == mac_num2 and mac_num != 0:
                # Convert to MAC address format
                mac_hex = f"{mac_num:012x}"
                mac = ":".join([mac_hex[i : i + 2] for i in range(0, 12, 2)])
                logger.debug(f"Found MAC address {mac} using uuid.getnode()")
                return mac
        except Exception as e:
            logger.debug(f"Failed to get MAC via uuid.getnode(): {e}")
        return None

    @staticmethod
    def _read_mac_from_interface(interface: str) -> str | None:
        """Read MAC address from a specific network interface."""
        try:
            mac_path = Path(f"/sys/class/net/{interface}/address")
            if mac_path.exists():
                mac = mac_path.read_text().strip().lower()
                return mac
        except Exception:
            pass
        return None

    @staticmethod
    def _get_primary_mac() -> str | None:
        """Get MAC address of primary network interface."""
        # Priority order: physical ethernet first, then wireless
        interfaces_priority = ["eth0", "end0", "enp0s3", "eno1", "wlan0", "wlp1s0"]

        # First try priority interfaces
        for interface in interfaces_priority:
            mac = DeviceIdentity._read_mac_from_interface(interface)
            if mac and mac != "00:00:00:00:00:00":
                logger.info(f"Using MAC from {interface}: {mac}")
                return mac

        # Fallback: get first non-virtual interface
        try:
            for interface_path in Path("/sys/class/net").glob("*"):
                interface = interface_path.name
                # Skip virtual interfaces
                if interface in ["lo"] or interface.startswith(("docker", "veth", "br-", "virbr")):
                    continue
                mac = DeviceIdentity._read_mac_from_interface(interface)
                if mac and mac != "00:00:00:00:00:00":
                    logger.info(f"Using MAC from {interface}: {mac}")
                    return mac
        except Exception as e:
            logger.debug(f"Failed to scan network interfaces: {e}")

        return None


class DeviceConfigManager:
    def __init__(self, config_file: Path | None = None):
        self.config_file = config_file or (get_state_dir() / "device_config.json")
        self.identity: DeviceIdentity | None = None

    def load_or_create(self) -> DeviceIdentity:
        """Load existing device identity or create a new one using MAC-based generation."""
        # Always try to get MAC-based identity first for consistency
        mac_identity = DeviceIdentity.generate_from_mac()

        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                    stored_identity = DeviceIdentity(**data)

                    # Check if stored identity matches MAC-based identity
                    if stored_identity.hostname == mac_identity.hostname:
                        self.identity = stored_identity
                        logger.info(f"Loaded existing MAC-based identity: {self.identity.hostname}")
                    else:
                        # MAC-based hostname differs from stored, update to MAC-based
                        logger.info(
                            f"Updating hostname from {stored_identity.hostname} "
                            f"to MAC-based {mac_identity.hostname}"
                        )
                        self.identity = mac_identity
                        self._save_identity()

                    # Always verify and update system configuration
                    if self._verify_system_config():
                        logger.debug("System configuration is correct")
                    else:
                        logger.info("System configuration needs update, reconfiguring...")
                        self._configure_system()
                        self._reload_avahi()

                    return self.identity
            except Exception as e:
                logger.error(f"Failed to load device config: {e}")
                # Fall through to create new MAC-based identity

        # Check if current hostname already matches our MAC-based pattern
        current_hostname = self._get_current_hostname()
        if current_hostname == mac_identity.hostname:
            logger.info(f"Current hostname already matches MAC-based: {current_hostname}")
            self.identity = mac_identity
        else:
            # Use MAC-based identity
            self.identity = mac_identity
            logger.info(f"Generated new MAC-based device identity: {self.identity.hostname}")

        # Save to file
        self._save_identity()

        # Configure system (hostname, /etc/hosts)
        self._configure_system()
        self._reload_avahi()

        return self.identity

    def _get_current_hostname(self) -> str | None:
        """Get the current system hostname."""
        try:
            result = subprocess.run(["hostname"], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get current hostname: {e}")
            return None

    def _reload_avahi(self) -> None:
        """Update avahi-daemon hostname using avahi-set-host-name or restart as fallback."""
        if not self.identity:
            logger.warning("No identity to set avahi hostname")
            return

        hostname = self.identity.hostname

        try:
            # First check if avahi-daemon is running
            check_result = subprocess.run(
                ["systemctl", "is-active", "avahi-daemon"], capture_output=True, text=True
            )

            if check_result.returncode != 0:
                logger.debug("avahi-daemon is not active, skipping hostname update")
                return

            # Try using avahi-set-host-name (preferred method)
            try:
                subprocess.run(
                    ["avahi-set-host-name", hostname], capture_output=True, text=True, check=True
                )
                logger.info(
                    f"Successfully set avahi hostname to {hostname} using avahi-set-host-name"
                )
                return
            except FileNotFoundError:
                logger.debug("avahi-set-host-name not found, falling back to restart method")
            except subprocess.CalledProcessError as e:
                logger.warning(f"avahi-set-host-name failed: {e.stderr}, falling back to restart")

            # Fallback: restart avahi-daemon (less preferred but works)
            try:
                subprocess.run(["systemctl", "restart", "avahi-daemon"], check=True)
                logger.info(f"Restarted avahi-daemon to pick up hostname {hostname}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to restart avahi-daemon: {e}")

        except FileNotFoundError:
            logger.debug("systemctl not found, skipping avahi reload")
        except Exception as e:
            logger.error(f"Unexpected error updating avahi hostname: {e}")

    def _verify_system_config(self) -> bool:
        """Verify that system configuration matches the saved identity."""
        if not self.identity:
            return False

        hostname = self.identity.hostname

        # Check if /etc/hostname matches
        try:
            with open("/etc/hostname") as f:
                current_hostname = f.read().strip()
                if current_hostname != hostname:
                    logger.debug(
                        f"Hostname mismatch: current={current_hostname}, expected={hostname}"
                    )
                    return False
        except Exception as e:
            logger.debug(f"Failed to read /etc/hostname: {e}")
            return False

        # Check if /etc/hosts has the correct entry
        try:
            with open("/etc/hosts") as f:
                hosts_content = f.read()
                # Look for the 127.0.1.1 entry with our hostname
                expected_entry = f"127.0.1.1\t{hostname}"
                if expected_entry not in hosts_content:
                    logger.debug("Hostname entry missing or incorrect in /etc/hosts")
                    return False
        except Exception as e:
            logger.debug(f"Failed to read /etc/hosts: {e}")
            return False

        # Check if actual system hostname matches
        try:
            result = subprocess.run(["hostname"], capture_output=True, text=True, check=True)
            system_hostname = result.stdout.strip()
            if system_hostname != hostname:
                logger.debug(
                    f"System hostname mismatch: current={system_hostname}, expected={hostname}"
                )
                return False
        except Exception as e:
            logger.debug(f"Failed to check system hostname: {e}")
            return False

        return True

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

            # Reload avahi-daemon to ensure it picks up the new hostname immediately
            self._reload_avahi()

        except Exception as e:
            logger.error(f"Failed to update hostname: {e}")

    def _update_hosts_file(self) -> None:
        """Update /etc/hosts with proper entries for mDNS."""

        if not self.identity:
            logger.error("No device identity to update /etc/hosts")
            return

        hostname = self.identity.hostname

        # Validate hostname before writing to hosts file
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", hostname):
            logger.error(f"Invalid hostname for hosts file: {hostname}")
            return

        # Additional check for special characters that could corrupt hosts file
        if any(char in hostname for char in ["\t", "\n", "\r", " ", "#"]):
            logger.error(f"Hostname contains invalid characters for hosts file: {hostname}")
            return

        try:
            # Create secure temp directory if it doesn't exist
            secure_temp_dir = Path("/var/tmp/distiller")
            secure_temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

            # Verify directory ownership and permissions
            dir_stat = secure_temp_dir.stat()
            if dir_stat.st_uid != 0:  # Must be owned by root
                logger.error("Secure temp directory has wrong ownership")
                return
            if dir_stat.st_mode & 0o077:  # Should not be accessible by others
                logger.error("Secure temp directory has insecure permissions")
                return

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

            # Create temp file in secure directory with restricted permissions
            temp_fd, temp_path = tempfile.mkstemp(
                dir=str(secure_temp_dir), prefix="hosts.", suffix=".tmp"
            )

            try:
                # Verify temp file is not a symlink
                temp_stat = os.fstat(temp_fd)
                path_stat = os.stat(temp_path)
                if not stat.S_ISREG(temp_stat.st_mode) or temp_stat.st_ino != path_stat.st_ino:
                    logger.error("Temp file security check failed - possible symlink attack")
                    raise ValueError("Temp file validation failed")

                # Write content with explicit file descriptor to prevent race conditions
                with os.fdopen(temp_fd, "w") as f:
                    f.writelines(updated_lines)
                temp_fd = None  # Mark as closed

                # Set proper permissions before moving
                os.chmod(temp_path, 0o644)

                # Try atomic replace first (works on same filesystem)
                try:
                    os.replace(temp_path, "/etc/hosts")
                    logger.info(f"Updated /etc/hosts with entry for {hostname} (atomic)")
                except OSError as e:
                    # If atomic replace fails (cross-filesystem or busy), use copy
                    if e.errno == 16 or e.errno == 18:  # EBUSY or EXDEV (cross-device link)
                        logger.debug(f"Atomic replace failed ({e}), using copy method")

                        # Create secure backup directory if it doesn't exist
                        backup_dir = Path("/var/backups/distiller")
                        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

                        # Rotate backups (keep last 3)
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = backup_dir / f"hosts.bak.{timestamp}"

                        # Remove old backups, keep only last 3
                        existing_backups = sorted(backup_dir.glob("hosts.bak.*"))
                        if len(existing_backups) >= 3:
                            for old_backup in existing_backups[:-2]:
                                try:
                                    old_backup.unlink()
                                    logger.debug(f"Removed old backup: {old_backup}")
                                except Exception:
                                    pass

                        # Create new backup with secure permissions
                        shutil.copy2("/etc/hosts", str(backup_path))
                        os.chmod(str(backup_path), 0o600)  # Only root can read/write
                        logger.debug(f"Created secure backup: {backup_path}")

                        try:
                            # Copy temp file content to /etc/hosts
                            shutil.copy2(temp_path, "/etc/hosts")
                            logger.info(f"Updated /etc/hosts with entry for {hostname} (copy)")
                        except Exception:
                            # Restore from backup on failure
                            shutil.copy2(str(backup_path), "/etc/hosts")
                            logger.error("Restored /etc/hosts from backup after failure")
                            raise
                    else:
                        raise

            finally:
                # Clean up temp file descriptor if still open
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except Exception:
                        pass
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
