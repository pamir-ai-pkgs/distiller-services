"""
Avahi service file manager for mDNS service advertisement.
"""

import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)


class AvahiService:
    """
    Manages Avahi service file for HTTP service advertisement.

    This creates/updates/removes an Avahi service file that announces
    our HTTP service via mDNS. Avahi handles all the complexity of
    hostname conflicts and network changes.
    """

    def __init__(self, port: int = 8080):
        self.port = port
        self.service_file = Path("/etc/avahi/services/distiller-wifi.service")
        self._running = False

    def start(self) -> None:
        """Create Avahi service file to start advertising."""
        if self._running:
            logger.warning("Avahi service already running")
            return

        try:
            # Get the device hostname
            hostname = socket.gethostname()

            # Ensure avahi-daemon has the correct hostname
            # This is critical for proper mDNS operation
            try:
                import subprocess
                import time

                # First try to get avahi's current hostname
                avahi_hostname = None
                try:
                    result = subprocess.run(
                        ["avahi-resolve", "--name", f"{hostname}.local"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if result.returncode == 0:
                        # Extract hostname from output
                        output = result.stdout.strip()
                        if output:
                            # Output format is usually "hostname.local\tIP"
                            avahi_hostname = output.split()[0].replace(".local", "")
                except Exception:
                    pass

                # If hostname doesn't match, update it
                if avahi_hostname != hostname:
                    logger.info(f"Updating avahi hostname from '{avahi_hostname}' to '{hostname}'")

                    # Try avahi-set-host-name first (preferred)
                    try:
                        subprocess.run(
                            ["avahi-set-host-name", hostname],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        logger.info(f"Successfully set avahi hostname to {hostname}")
                        time.sleep(0.5)  # Give avahi a moment to update
                    except FileNotFoundError:
                        # avahi-set-host-name not available, fallback to restart
                        logger.debug("avahi-set-host-name not found, restarting avahi-daemon")
                        subprocess.run(["systemctl", "restart", "avahi-daemon"], check=False)
                        time.sleep(1)  # Give avahi more time after restart
                    except subprocess.CalledProcessError as e:
                        # Command failed, try restart as fallback
                        logger.warning(f"avahi-set-host-name failed: {e}, restarting avahi-daemon")
                        subprocess.run(["systemctl", "restart", "avahi-daemon"], check=False)
                        time.sleep(1)
            except Exception as e:
                # Hostname verification is important but not fatal
                logger.warning(f"Could not verify/update avahi hostname: {e}")

            # Create the service XML
            service_xml = f"""<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>Distiller WiFi Setup</name>
  <service>
    <type>_http._tcp</type>
    <port>{self.port}</port>
    <txt-record>path=/</txt-record>
    <txt-record>version=2.0</txt-record>
    <txt-record>device=distiller</txt-record>
  </service>
</service-group>
"""

            # Ensure the services directory exists
            self.service_file.parent.mkdir(parents=True, exist_ok=True)

            # Write the service file
            self.service_file.write_text(service_xml)

            self._running = True
            logger.info(f"Created Avahi service file for {hostname} on port {self.port}")

        except Exception as e:
            logger.error(f"Failed to create Avahi service file: {e}")

    def stop(self) -> None:
        """Remove Avahi service file to stop advertising."""
        if not self._running:
            return

        try:
            # Remove the service file if it exists
            if self.service_file.exists():
                self.service_file.unlink()
                logger.info("Removed Avahi service file")

            self._running = False

        except Exception as e:
            logger.error(f"Failed to remove Avahi service file: {e}")

    def update_port(self, port: int) -> None:
        """Update the advertised port number."""
        if port == self.port:
            return

        self.port = port

        # Recreate the service file with new port
        if self._running:
            self.stop()
            self.start()
            logger.info(f"Updated Avahi service port to {port}")

    def cleanup(self) -> None:
        """Clean up on exit."""
        self.stop()
