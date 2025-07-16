"""
Display module for Distiller CM5 Services

Provides e-ink display functionality for WiFi setup and status information.
"""

from .eink_display import EinkDisplay, get_display

__all__ = ['EinkDisplay', 'get_display']