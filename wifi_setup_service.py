#!/usr/bin/env python3
"""
WiFi Setup Service - Main Orchestration Script

Creates a WiFi hotspot and web interface for device configuration.
Monitors for successful connections and handles cleanup.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

import uvicorn
from network.wifi_manager import WiFiManager, WiFiManagerError
from network.wifi_server import WiFiServer
from mdns_service import MDNSService

# Import evdev for button checking
try:
    import evdev
    from evdev import InputDevice, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    print("Warning: evdev package not available - button monitoring disabled")
    EVDEV_AVAILABLE = False

# Import eink display functionality
try:
    from eink_display_flush import SimpleEinkDriver, load_and_convert_image
    from wifi_info_display import create_wifi_info_image, create_wifi_setup_image, create_wifi_success_image
    EINK_AVAILABLE = True
except ImportError as e:
    print(f"Warning: eink functionality not available - {e}")
    EINK_AVAILABLE = False


class WiFiSetupService:
    """Main WiFi setup service orchestrator"""

    def __init__(
        self, 
        hotspot_ssid: str = "SetupWiFi", 
        hotspot_password: str = "setupwifi123",
        device_name: str = "Pamir AI Key Input",
        check_button: bool = True,
        enable_eink: bool = True,
        mdns_hostname: str = "distiller",
        mdns_port: int = 8000
    ):
        self.hotspot_ssid = hotspot_ssid
        self.hotspot_password = hotspot_password
        self.device_name = device_name
        self.check_button = check_button and EVDEV_AVAILABLE
        self.enable_eink = enable_eink and EINK_AVAILABLE
        self.mdns_hostname = mdns_hostname
        self.mdns_port = mdns_port
        self.device_path = None
        self.check_duration = 2.0  # seconds to check for button hold
        
        self.wifi_manager = WiFiManager()
        self.wifi_server = WiFiServer(self.wifi_manager)
        self.server = None
        self.mdns_service = None
        self.running = False

        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Log eink status
        if not enable_eink:
            self.logger.info("E-ink display disabled by configuration")
        elif not EINK_AVAILABLE:
            self.logger.info("E-ink display not available (missing dependencies)")
        else:
            self.logger.info("E-ink display enabled and available")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def setup_logging(self):
        """Configure logging with file and console output"""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        # Try to write to system log first, fallback to local
        log_paths = ["/var/log/wifi-setup.log", "./wifi-setup.log"]
        log_file = None

        for path in log_paths:
            try:
                # Test write access
                Path(path).touch(exist_ok=True)
                log_file = path
                break
            except (PermissionError, OSError):
                continue

        # Configure logging - force reconfiguration
        # Clear any existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
            
        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file:
            handlers.append(logging.FileHandler(log_file))

        logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers, force=True)

        if log_file:
            print(f"Logging to: {log_file}")
        else:
            print("Warning: Could not write to log file, using console only")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def find_device(self) -> bool:
        """Find the input device by name"""
        if not EVDEV_AVAILABLE:
            return False
            
        try:
            devices = [InputDevice(path) for path in evdev.list_devices()]
            for device in devices:
                self.logger.debug(f"Checking device: {device.path}, Name: {device.name}")
                if device.name == self.device_name:
                    self.device_path = device.path
                    self.logger.info(f"Found device '{self.device_name}' at path: {device.path}")
                    return True
            
            self.logger.warning(f"Could not find input device with name: '{self.device_name}'")
            return False
        except Exception as e:
            self.logger.error(f"Error finding device: {e}")
            return False

    def is_enter_button_held(self) -> bool:
        """Check if ENTER button is currently being held"""
        if not self.device_path or not EVDEV_AVAILABLE:
            return False
        
        try:
            device = InputDevice(self.device_path)
            
            # Get the current state of all keys
            active_keys = device.active_keys()
            
            # Check if ENTER key is in the active keys
            is_held = ecodes.KEY_ENTER in active_keys
            
            device.close()
            return is_held
            
        except Exception as e:
            self.logger.error(f"Error checking button state: {e}")
            return False

    def check_button_during_startup(self) -> bool:
        """Check if button is held during the startup check period"""
        if not self.check_button:
            return False
            
        self.logger.info(f"Checking for ENTER button hold for {self.check_duration} seconds...")
        
        start_time = time.time()
        samples_held = 0
        total_samples = 0
        
        while time.time() - start_time < self.check_duration:
            if self.is_enter_button_held():
                samples_held += 1
            total_samples += 1
            time.sleep(0.1)  # Check every 100ms
        
        # Consider button held if it was held for at least 80% of the time
        hold_ratio = samples_held / total_samples if total_samples > 0 else 0
        is_consistently_held = hold_ratio >= 0.8
        
        self.logger.info(f"Button hold ratio: {hold_ratio:.2f} ({samples_held}/{total_samples} samples)")
        
        if is_consistently_held:
            self.logger.info("ENTER button consistently held during startup - triggering WiFi setup!")
            return True
        else:
            self.logger.info("ENTER button not consistently held - normal startup")
            return False

    def display_wifi_info(self):
        """Display WiFi information on eink display"""
        if not self.enable_eink:
            self.logger.debug("E-ink display disabled - skipping WiFi info display")
            return
            
        try:
            self.logger.info("Displaying WiFi information on eink display...")
            
            # Create and automatically display WiFi info image on eink
            create_wifi_info_image(
                width=240, 
                height=416, 
                filename="wifi_info.png", 
                auto_display=True
            )
            
            self.logger.info("WiFi information displayed successfully on eink")
                
        except Exception as e:
            self.logger.error(f"Error displaying WiFi info: {e}")

    def display_setup_instructions(self):
        """Display setup instructions on e-ink screen"""
        if not self.enable_eink:
            self.logger.debug("E-ink display disabled - skipping setup instructions display")
            return
            
        try:
            # Get the hotspot IP address
            hotspot_ip = "192.168.4.1"  # Default hotspot IP
            
            self.logger.info("Displaying setup instructions on e-ink screen...")
            create_wifi_setup_image(
                ssid=self.hotspot_ssid,
                password=self.hotspot_password,
                ip_address=hotspot_ip,
                port=8080,
                filename="wifi_setup_instructions.png",
                auto_display=True
            )
            self.logger.info("Setup instructions displayed on e-ink screen")
        except Exception as e:
            self.logger.error(f"Failed to display setup instructions on e-ink: {e}")

    def display_success_screen(self, connection_info):
        """Display success screen on e-ink"""
        if not self.enable_eink:
            self.logger.debug("E-ink display disabled - skipping success screen display")
            return
            
        try:
            self.logger.info("Displaying success screen on e-ink...")
            create_wifi_success_image(
                ssid=connection_info.get('ssid', 'Unknown'),
                ip_address=connection_info.get('ip_address', 'Unknown'),
                filename="wifi_setup_success.png",
                auto_display=True
            )
            self.logger.info("Success screen displayed on e-ink")
        except Exception as e:
            self.logger.error(f"Failed to display success screen on e-ink: {e}")

    async def start_mdns_service(self):
        """Start mDNS service for post-connection access"""
        try:
            self.logger.info(f"Starting mDNS service: {self.mdns_hostname}.local:{self.mdns_port}")
            
            self.mdns_service = MDNSService(
                hostname=self.mdns_hostname,
                service_name="Pamir AI Device",
                port=self.mdns_port
            )
            
            # Start the mDNS web server
            mdns_server_task = await self.mdns_service.start_web_server()
            
            self.logger.info(f"mDNS service active: http://{self.mdns_hostname}.local:{self.mdns_port}")
            print(f"\nSetup Complete!")
            print(f"Device accessible at:")
            print(f"   * mDNS: http://{self.mdns_hostname}.local:{self.mdns_port}")
            print(f"   * Direct IP: http://{self.mdns_service.get_local_ip()}:{self.mdns_port}")
            print(f"\nNow you can use Cursor to play with MCP!")
            print(f"Note: If .local doesn't work, use the direct IP address")
            # print(f"To enable mDNS on Linux: sudo systemctl enable --now avahi-daemon\n")
            
            return mdns_server_task
            
        except Exception as e:
            self.logger.error(f"Failed to start mDNS service: {e}")
            return None

    async def wait_for_network(self, max_wait=30):
        """Wait for network connectivity before proceeding"""
        self.logger.info("Waiting for network connectivity...")
        
        import subprocess
        
        for attempt in range(max_wait):
            try:
                # Check if we have any network connectivity
                result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.logger.info(f"Network connectivity detected after {attempt + 1} seconds")
                    # Give WiFi a bit more time to fully establish
                    await asyncio.sleep(3)
                    return True
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                pass
            
            await asyncio.sleep(1)
        
        self.logger.warning(f"No network connectivity after {max_wait} seconds, proceeding anyway")
        return False

    async def run_startup_check(self):
        """Run startup check for button hold and display WiFi info if not in setup mode"""
        self.logger.info("=== WiFi Setup Startup Check ===")
        
        # Wait a moment for system to stabilize
        self.logger.info("Waiting for system to stabilize...")
        await asyncio.sleep(1)
        
        # Wait for network connectivity (but don't fail if it doesn't come)
        await self.wait_for_network(max_wait=20)
        
        # Find the input device if button checking is enabled
        if self.check_button:
            if not self.find_device():
                self.logger.error("Could not find input device - skipping button check")
                self.check_button = False
        
        # Check if button is held during startup
        if self.check_button and self.check_button_during_startup():
            # Button was held - start WiFi setup
            self.logger.info("Button held - starting WiFi setup mode")
            return True
        
        # Check if there's any WiFi connection (auto-setup mode)
        try:
            self.logger.info("Checking current WiFi connection status...")
            status = await self.wifi_manager.get_connection_status()
            
            if not status.connected:
                self.logger.info("No WiFi connection detected - automatically starting WiFi setup mode")
                return True
            elif status.ssid and not status.ssid.startswith("SetupWiFi"):
                # Connected to a real WiFi network
                self.logger.info(f"Already connected to WiFi network: {status.ssid}")
                self.logger.info("No WiFi setup trigger detected - displaying WiFi info")
                self.display_wifi_info()
                return False
            else:
                # Connected to our own setup hotspot or similar - start setup
                self.logger.info(f"Connected to setup/hotspot network ({status.ssid}) - starting WiFi setup mode")
                return True
                
        except Exception as e:
            self.logger.error(f"Error checking WiFi status: {e}")
            # If we can't check status, assume we need setup
            self.logger.info("Unable to determine WiFi status - starting WiFi setup mode as fallback")
            return True

    async def start_hotspot(self) -> bool:
        """Start the WiFi hotspot"""
        try:
            self.logger.info(f"Starting hotspot: {self.hotspot_ssid}")
            success = await self.wifi_manager.start_hotspot(
                self.hotspot_ssid, self.hotspot_password
            )

            if success:
                self.logger.info("Hotspot started")
                # Display setup instructions on e-ink
                self.display_setup_instructions()
                return True
            else:
                self.logger.error("Failed to start hotspot")
                return False

        except WiFiManagerError as e:
            self.logger.error(f"Hotspot startup failed: {e}")
            return False

    async def start_web_server(self):
        """Start the web server in background"""
        try:
            config = uvicorn.Config(
                self.wifi_server.app,
                host="0.0.0.0",
                port=8080,
                log_level="warning",  # Reduce uvicorn noise
                access_log=False,
            )

            self.server = uvicorn.Server(config)
            self.logger.info("Starting web server on port 8080")

            # Run server in background task
            server_task = asyncio.create_task(self.server.serve())
            return server_task

        except Exception as e:
            self.logger.error(f"Failed to start web server: {e}")
            raise

    async def monitor_connection(self) -> bool:
        """Monitor for successful WiFi connection"""
        self.logger.info("Monitoring for WiFi connection")

        connection_timeout = 300  # 5 minutes
        check_interval = 5  # seconds
        start_time = time.time()

        while self.running and (time.time() - start_time) < connection_timeout:
            try:
                status = await self.wifi_manager.get_connection_status()
                
                # Add debug logging to understand connection status
                self.logger.debug(f"Connection status: connected={status.connected}, ssid={status.ssid}, hotspot_ssid={self.hotspot_ssid}")

                if status.connected and status.ssid != self.hotspot_ssid:
                    self.logger.info(f"Connected to: {status.ssid}")

                    # Display success screen
                    connection_info = {
                        'ssid': status.ssid,
                        'ip_address': getattr(status, 'ip_address', 'Unknown')
                    }
                    self.display_success_screen(connection_info)

                    # Stop the hotspot
                    if self.wifi_manager._hotspot_active:
                        await self.wifi_manager.stop_hotspot()

                    # Start mDNS service for post-connection access
                    # mdns_server_task = await self.start_mdns_service()
                    
                    # if mdns_server_task:
                    #     # Keep the mDNS service running - don't wait for it to complete
                    #     # It will run in the background to serve the "Cursor MCP" page
                    #     pass

                    # Keep server running for 2 minutes to allow status page to reconnect via WiFi
                    self.logger.info("WiFi connection successful - keeping server running for 2 minutes to allow status page reconnection")
                    await asyncio.sleep(120)
                    self.logger.info("2-minute grace period completed")

                    return True
                elif status.connected:
                    self.logger.debug(f"Connected but to hotspot ({status.ssid}), continuing to monitor")
                else:
                    self.logger.debug("Not connected, continuing to monitor")

                await asyncio.sleep(check_interval)

            except Exception as e:
                self.logger.error(f"Connection monitoring error: {e}")
                await asyncio.sleep(check_interval)

        if not self.running:
            self.logger.info("Monitoring stopped by user")
        else:
            self.logger.warning("Connection monitoring timed out")

        return False

    async def cleanup(self):
        """Clean up resources and stop services"""
        self.logger.info("Cleaning up services")

        try:
            # Stop web server
            if self.server:
                self.logger.info("Stopping web server...")
                self.server.should_exit = True
                await asyncio.sleep(1)  # Give server time to stop

            # Stop mDNS service
            # if self.mdns_service:
            #     self.logger.info("Stopping mDNS service...")
            #     await self.mdns_service.stop_web_server()

            # Stop hotspot
            self.logger.info("Stopping hotspot...")
            await self.wifi_manager.stop_hotspot()

            self.logger.info("Cleanup completed")

        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

    def print_connection_info(self):
        """Print connection instructions"""
        print("\n" + "=" * 60)
        print("WiFi Setup Service Started")
        print("=" * 60)
        print(f"Hotspot Name: {self.hotspot_ssid}")
        print(f"Password: {self.hotspot_password}")
        print("Web Interface: http://192.168.4.1:8080")
        print(f"E-ink Display: {'Enabled' if self.enable_eink else 'Disabled'}")
        print(f"Button Check: {'Enabled' if self.check_button else 'Disabled'}")
        print("\nSetup Instructions:")
        print("1. Connect your device to the hotspot above")
        print("2. Open a web browser and visit: http://192.168.4.1:8080")
        print("3. Enter the WiFi network name (SSID) you want to connect to")
        print("4. Enter the network password (leave empty for open networks)")
        print("5. Click 'Connect' and wait for confirmation")
        print("6. Setup will complete automatically on successful connection")
        print("\nPress Ctrl+C to stop the service")
        print("=" * 60 + "\n")

    async def run(self, check_startup: bool = True):
        """Main service execution"""
        self.running = True

        try:
            # Run startup check if requested
            if check_startup:
                should_setup = await self.run_startup_check()
                if not should_setup:
                    # No setup needed, just displayed WiFi info
                    return True

            # Start hotspot
            if not await self.start_hotspot():
                return False

            # Start web server
            server_task = await self.start_web_server()

            # Print connection info
            self.print_connection_info()

            # Wait a moment for server to start
            await asyncio.sleep(2)

            # Monitor for connections with graceful handling
            try:
                connection_task = asyncio.create_task(self.monitor_connection())

                # Wait for either connection success or manual interruption
                done, pending = await asyncio.wait(
                    [connection_task, server_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if we got a successful connection
                if connection_task in done:
                    connected = await connection_task
                    if connected:
                        self.logger.info("Setup completed successfully")
                        await asyncio.sleep(3)
                        return True

            except asyncio.CancelledError:
                self.logger.info("Service interrupted by user")

            return False

        except Exception as e:
            self.logger.error(f"Service error: {e}")
            return False
        finally:
            await self.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="WiFi Setup Service - Create hotspot for WiFi configuration"
    )
    parser.add_argument(
        "--ssid",
        default=os.getenv("WIFI_HOTSPOT_SSID", "SetupWiFi"),
        help="Hotspot SSID (default: SetupWiFi)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("WIFI_HOTSPOT_PASSWORD", "setupwifi123"),
        help="Hotspot password (default: setupwifi123)",
    )
    parser.add_argument(
        "--device-name",
        default="Pamir AI Key Input",
        help="Input device name for button detection (default: Pamir AI Key Input)",
    )
    parser.add_argument(
        "--no-button-check",
        action="store_true",
        help="Disable button checking and always run setup mode",
    )
    parser.add_argument(
        "--no-startup-check",
        action="store_true",
        help="Skip startup check and go directly to setup mode",
    )
    parser.add_argument(
        "--no-eink",
        action="store_true",
        default=os.getenv("WIFI_SETUP_NO_EINK", "false").lower() in ("true", "1", "yes"),
        help="Disable e-ink display functionality (useful for testing without hardware). Can also be set via WIFI_SETUP_NO_EINK=true",
    )
    parser.add_argument(
        "--mdns-hostname",
        default="distiller",
        help="mDNS hostname for post-connection access (default: distiller)",
    )
    parser.add_argument(
        "--mdns-port",
        type=int,
        default=8000,
        help="Port for mDNS web service (default: 8000)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Adjust logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check for root privileges
    if os.geteuid() != 0:
        print(
            "Error: This service requires root privileges for NetworkManager operations"
        )
        print("Please run with: sudo python wifi_setup_service.py")
        sys.exit(1)

    # Create and run service
    service = WiFiSetupService(
        args.ssid, 
        args.password, 
        args.device_name,
        check_button=not args.no_button_check,
        enable_eink=not args.no_eink,
        mdns_hostname=args.mdns_hostname,
        mdns_port=args.mdns_port
    )

    try:
        success = asyncio.run(service.run(check_startup=not args.no_startup_check))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nService stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
