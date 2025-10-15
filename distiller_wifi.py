#!/usr/bin/env python3
"""Development wrapper for Distiller WiFi Provisioning System.

This is a convenience script for development. The actual package entry point
is at src/distiller_services/__main__.py

For production use, install the package and use: distiller-wifi
For development, use: python -m distiller_services
"""

if __name__ == "__main__":
    import sys

    from distiller_services.__main__ import main

    sys.exit(main())
