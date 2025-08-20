"""Captive Portal management for automatic browser popup."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class CaptivePortal:
    """Manages captive portal functionality including iptables rules and detection."""

    def __init__(self, interface: str, gateway_ip: str, web_port: int):
        self.interface = interface
        self.gateway_ip = gateway_ip
        self.web_port = web_port
        self.enabled = False
        self._iptables_rules_applied = False

    async def enable(self) -> bool:
        """Enable captive portal by setting up iptables rules."""
        if self.enabled:
            logger.debug("Captive portal already enabled")
            return True

        try:
            # Add iptables rules to redirect HTTP/HTTPS traffic to our web server
            await self._apply_iptables_rules()
            self.enabled = True
            logger.info(f"Captive portal enabled on {self.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable captive portal: {e}")
            return False

    async def disable(self) -> bool:
        """Disable captive portal by removing iptables rules."""
        if not self.enabled:
            logger.debug("Captive portal already disabled")
            return True

        try:
            await self._remove_iptables_rules()
            self.enabled = False
            logger.info("Captive portal disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable captive portal: {e}")
            return False

    async def _apply_iptables_rules(self) -> None:
        """Apply iptables rules for traffic redirection."""
        if self._iptables_rules_applied:
            await self._remove_iptables_rules()

        commands = [
            # Redirect HTTP traffic (port 80) to our web server port
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-i",
                self.interface,
                "-p",
                "tcp",
                "--dport",
                "80",
                "-j",
                "REDIRECT",
                "--to-port",
                str(self.web_port),
            ],
            # Optionally redirect HTTPS for detection (port 443)
            # Note: This won't work for actual HTTPS traffic but helps with some detection
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-i",
                self.interface,
                "-p",
                "tcp",
                "--dport",
                "443",
                "-j",
                "REDIRECT",
                "--to-port",
                str(self.web_port),
            ],
            # Allow traffic from the gateway itself (so our server works)
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "OUTPUT",
                "-p",
                "tcp",
                "-d",
                self.gateway_ip,
                "--dport",
                "80",
                "-j",
                "ACCEPT",
            ],
        ]

        for cmd in commands:
            await self._run_command(cmd)
            logger.debug(f"Applied iptables rule: {' '.join(cmd)}")

        self._iptables_rules_applied = True

    async def _remove_iptables_rules(self) -> None:
        """Remove iptables rules for traffic redirection."""
        if not self._iptables_rules_applied:
            return

        # Convert -A (append) to -D (delete) for removal
        commands = [
            [
                "iptables",
                "-t",
                "nat",
                "-D",
                "PREROUTING",
                "-i",
                self.interface,
                "-p",
                "tcp",
                "--dport",
                "80",
                "-j",
                "REDIRECT",
                "--to-port",
                str(self.web_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-D",
                "PREROUTING",
                "-i",
                self.interface,
                "-p",
                "tcp",
                "--dport",
                "443",
                "-j",
                "REDIRECT",
                "--to-port",
                str(self.web_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-D",
                "OUTPUT",
                "-p",
                "tcp",
                "-d",
                self.gateway_ip,
                "--dport",
                "80",
                "-j",
                "ACCEPT",
            ],
        ]

        for cmd in commands:
            try:
                await self._run_command(cmd)
                logger.debug(f"Removed iptables rule: {' '.join(cmd)}")
            except Exception as e:
                # Rule might not exist, that's okay
                logger.debug(f"Could not remove iptables rule (may not exist): {e}")

        self._iptables_rules_applied = False

    async def _run_command(self, cmd: list[str]) -> tuple[int, str, str]:
        """Run a shell command and return the result."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return (
                process.returncode,
                stdout.decode("utf-8").strip(),
                stderr.decode("utf-8").strip(),
            )
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise

    def is_captive_portal_check(self, path: str, user_agent: str | None = None) -> bool:
        """Check if the request is a captive portal detection request."""
        # Common captive portal detection URLs
        detection_paths = [
            "/generate_204",  # Android
            "/gen_204",  # Android alternate
            "/hotspot-detect.html",  # iOS/macOS
            "/library/test/success.html",  # iOS/macOS alternate
            "/success.txt",  # iOS alternate
            "/ncsi.txt",  # Windows
            "/connecttest.txt",  # Windows 10
            "/canonical.html",  # Firefox
            "/success.html",  # Generic
            "/kindle-wifi/wifistub.html",  # Kindle
        ]

        if path in detection_paths:
            return True

        # Check for captive portal user agents
        if user_agent:
            captive_agents = [
                "CaptiveNetworkSupport",  # iOS/macOS
                "Microsoft NCSI",  # Windows
                "Microsoft-CryptoAPI",  # Windows
                "Dalvik",  # Android
                "WiFi",  # Generic WiFi clients
            ]
            return any(agent in user_agent for agent in captive_agents)

        return False

    def get_detection_response(self, path: str) -> tuple[int, str, dict]:
        """Get the appropriate response for captive portal detection requests."""
        # Return responses that trigger captive portal popup
        if path == "/generate_204" or path == "/gen_204":
            # Android expects 204 No Content for internet, redirect for portal
            return 302, "", {"Location": f"http://{self.gateway_ip}:{self.web_port}/"}

        elif path in ["/hotspot-detect.html", "/library/test/success.html"]:
            # iOS expects "Success" for internet, anything else triggers portal
            return 200, "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>", {}

        elif path == "/success.txt":
            # iOS alternate
            return 200, "success", {}

        elif path == "/ncsi.txt":
            # Windows expects "Microsoft NCSI"
            return 200, "Microsoft NCSI", {}

        elif path == "/connecttest.txt":
            # Windows 10
            return 200, "Microsoft Connect Test", {}

        elif path == "/canonical.html":
            # Firefox
            return 200, "<html><head><title>Success</title></head><body>Success</body></html>", {}

        else:
            # Default redirect to portal
            return 302, "", {"Location": f"http://{self.gateway_ip}:{self.web_port}/"}
