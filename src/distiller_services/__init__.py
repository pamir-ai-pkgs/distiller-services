"""Distiller WiFi Provisioning Service.

Modern async WiFi provisioning system for Distiller edge computing devices.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("distiller-services")
except PackageNotFoundError:
    __version__ = "unknown"

__author__ = "PamirAI Incorporated"
__email__ = "support@pamir.ai"

__all__ = ["__version__", "__author__", "__email__"]
