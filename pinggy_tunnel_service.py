#!/usr/bin/env python3
"""
Pinggy Tunnel Service - SSH Tunnel Manager with WiFi Info Display Integration

Creates and maintains an SSH tunnel through Pinggy with hourly refresh
and updates the WiFi info display with tunnel QR code.
"""

import asyncio
import json
import logging
import os
import re
import select
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from wifi_info_display import create_wifi_info_image
from network.network_utils import NetworkUtils

class PinggyTunnelManager:
    """Manages SSH tunnels through Pinggy with automatic refresh"""
    
    def __init__(
        self,
        local_port: int = 3000,
        ssh_port: int = 443,
        refresh_interval: int = 3300,  # 55 minutes (before 1 hour expiry)
        enable_display: bool = True,
    ):
        self.local_port = local_port
        self.ssh_port = ssh_port
        self.refresh_interval = refresh_interval
        self.enable_display = enable_display
        
        self.current_process: Optional[subprocess.Popen] = None
        self.current_url: Optional[str] = None
        self.running = False
        
        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Network utilities
        self.network_utils = NetworkUtils()
    
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
            ]
        )
    
    def check_network_connectivity(self) -> bool:
        """Check if network is connected"""
        try:
            wifi_name = self.network_utils.get_wifi_name()
            ip_address = self.network_utils.get_wifi_ip_address()
            
            if wifi_name and ip_address and ip_address != "No IP":
                self.logger.info(f"Network connected: {wifi_name} ({ip_address})")
                return True
            else:
                self.logger.warning("No network connectivity detected")
                return False
        except Exception as e:
            self.logger.error(f"Error checking network: {e}")
            return False
    
    def extract_pinggy_url(self, output: str) -> Optional[str]:
        """Extract the Pinggy URL from SSH output"""
        # Pinggy typically outputs: "https://xxxxx.free.pinggy.link"
        # Try multiple patterns
        patterns = [
            r'https://[a-zA-Z0-9\-]+\.free\.pinggy\.link',
            r'http://[a-zA-Z0-9\-]+\.free\.pinggy\.link',
            r'[a-zA-Z0-9\-]+\.free\.pinggy\.link',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                url = match.group(0)
                # Ensure it has https://
                if not url.startswith('http'):
                    url = f'https://{url}'
                self.logger.debug(f"Found URL: {url}")
                return url
        return None
    
    async def start_tunnel(self) -> Optional[str]:
        """Start a new SSH tunnel and return the URL"""
        if self.current_process:
            self.stop_tunnel()
        
        cmd = [
            'ssh', '-p', str(self.ssh_port),
            '-R0:localhost:' + str(self.local_port),
            '-L4300:localhost:4300',  # Web Debugger API
            'a.pinggy.io',  # Use a.pinggy.io for API support
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ServerAliveInterval=30',
            '-o', 'ServerAliveCountMax=3',
            '-o', 'UserKnownHostsFile=/dev/null',
        ]
        
        try:
            self.logger.info(f"Starting SSH tunnel: {' '.join(cmd)}")
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=0,  # Unbuffered
            )
            
            # Give SSH time to establish connection
            self.logger.info("Waiting for tunnel to establish...")
            await asyncio.sleep(5)
            
            # Check if SSH process is still running
            if self.current_process.poll() is not None:
                # Read any error output
                stdout, stderr = self.current_process.communicate()
                self.logger.error(f"SSH process exited with code: {self.current_process.returncode}")
                self.logger.error(f"STDOUT: {stdout}")
                self.logger.error(f"STDERR: {stderr}")
                return None
            
            # Use Web Debugger API to get tunnel URLs
            import aiohttp
            start_time = time.time()
            timeout = 30
            
            while time.time() - start_time < timeout:
                if self.current_process.poll() is not None:
                    stdout, stderr = self.current_process.communicate()
                    self.logger.error(f"SSH process terminated unexpectedly with code: {self.current_process.returncode}")
                    self.logger.error(f"STDOUT: {stdout}")
                    self.logger.error(f"STDERR: {stderr}")
                    return None
                
                try:
                    # Query the Web Debugger API
                    self.logger.info("Attempting to query Pinggy API at http://localhost:4300/urls")
                    async with aiohttp.ClientSession() as session:
                        async with session.get('http://localhost:4300/urls', timeout=aiohttp.ClientTimeout(total=2)) as response:
                            if response.status == 200:
                                # API returns text/plain but contains JSON
                                text = await response.text()
                                import json
                                data = json.loads(text)
                                # API returns {"urls": [...]}
                                if isinstance(data, dict) and 'urls' in data:
                                    urls = data['urls']
                                elif isinstance(data, list):
                                    urls = data
                                else:
                                    continue
                                    
                                if urls and len(urls) > 0:
                                    # Prefer HTTPS URL
                                    for url in urls:
                                        if url.startswith('https://'):
                                            self.current_url = url
                                            self.logger.info(f"Tunnel established: {url}")
                                            return url
                                    # Fallback to first URL
                                    self.current_url = urls[0]
                                    self.logger.info(f"Tunnel established: {urls[0]}")
                                    return urls[0]
                except aiohttp.ClientError as e:
                    self.logger.debug(f"API connection error: {e}")
                except Exception as e:
                    self.logger.warning(f"API error: {type(e).__name__}: {e}")
                
                await asyncio.sleep(2)
            
            self.logger.error("Timeout waiting for Pinggy URL from API")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to start tunnel: {e}")
            return None
    
    def stop_tunnel(self):
        """Stop the current SSH tunnel"""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                self.current_process.wait()
            except Exception as e:
                self.logger.error(f"Error stopping tunnel: {e}")
            finally:
                self.current_process = None
                self.current_url = None
    
    async def update_display(self, url: str):
        """Update WiFi info display with tunnel URL"""
        if not self.enable_display:
            return
        
        try:
            # Create WiFi info image with tunnel URL
            create_wifi_info_image(
                filename="wifi_info_tunnel.png",
                auto_display=True,
                tunnel_url=url
            )
            self.logger.info("Display updated with tunnel QR code")
        except Exception as e:
            self.logger.error(f"Failed to update display: {e}")
    
    async def wait_for_network(self):
        """Wait for network connectivity before starting tunnel"""
        self.logger.info("Waiting for network connectivity...")
        
        while self.running:
            if self.check_network_connectivity():
                self.logger.info("Network is ready")
                return True
            
            await asyncio.sleep(5)  # Check every 5 seconds
        
        return False
    
    async def run_forever(self):
        """Main loop - maintain tunnel with periodic refresh"""
        self.running = True
        
        # Wait for network connectivity first
        if not await self.wait_for_network():
            self.logger.error("Service stopped before network was ready")
            return
        
        # Give WiFi setup service time to complete its display
        self.logger.info("Waiting 10 seconds for WiFi setup to complete...")
        await asyncio.sleep(10)
        
        while self.running:
            try:
                # Check network connectivity
                if not self.check_network_connectivity():
                    self.logger.warning("Lost network connectivity, waiting...")
                    await self.wait_for_network()
                    continue
                
                # Start or restart tunnel
                url = await self.start_tunnel()
                if url:
                    await self.update_display(url)
                    
                    # Wait for refresh interval
                    self.logger.info(f"Next refresh in {self.refresh_interval} seconds")
                    await asyncio.sleep(self.refresh_interval)
                else:
                    # Retry after short delay if failed
                    self.logger.warning("Failed to establish tunnel, retrying in 30 seconds")
                    await asyncio.sleep(30)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(30)
        
        # Cleanup
        self.stop_tunnel()
        self.logger.info("Tunnel service stopped")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        self.stop_tunnel()


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pinggy SSH Tunnel Service')
    parser.add_argument('--port', type=int, default=3000, help='Local port to tunnel')
    parser.add_argument('--ssh-port', type=int, default=443, help='SSH port for Pinggy')
    parser.add_argument('--refresh', type=int, default=3300, help='Refresh interval in seconds')
    parser.add_argument('--no-display', action='store_true', help='Disable display updates')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Adjust logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run tunnel manager
    manager = PinggyTunnelManager(
        local_port=args.port,
        ssh_port=args.ssh_port,
        refresh_interval=args.refresh,
        enable_display=not args.no_display,
    )
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        manager.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run service
    try:
        await manager.run_forever()
    except KeyboardInterrupt:
        manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())