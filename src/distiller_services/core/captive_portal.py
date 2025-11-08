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
            # Allow direct access to web server port (8080) without redirection
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
                str(self.web_port),
                "-j",
                "ACCEPT",
            ],
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
                str(self.web_port),
                "-j",
                "ACCEPT",
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
