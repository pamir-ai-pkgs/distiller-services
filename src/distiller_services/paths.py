"""
Centralized path management for development and production environments.

This module provides automatic detection of development vs production environments
and returns appropriate paths for state, logs, templates, static files, and SDK.

Environment variables can override any path:
- DISTILLER_STATE_DIR: State storage directory
- DISTILLER_LOG_DIR: Log directory
- DISTILLER_TEMPLATES_DIR: Jinja2 templates directory
- DISTILLER_STATIC_DIR: Static files (CSS, JS, fonts)
- DISTILLER_SDK_PATH: Distiller SDK source path
- DISTILLER_DEVICE_ENV_PATH: Device environment file

Development mode is auto-detected by checking if templates/ and static/
directories exist relative to the source tree root.
"""

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _is_development() -> bool:
    """Detect if running in development environment.

    Returns True if:
    - Running from source checkout (templates/ and static/ exist in project root)
    - Not installed to system paths

    Returns:
        True if in development mode, False if in production
    """
    # Get project root (3 levels up from src/distiller_services/paths.py)
    project_root = Path(__file__).parent.parent.parent

    # Check if we have local templates and static directories
    has_templates = (project_root / "templates").exists()
    has_static = (project_root / "static").exists()

    return has_templates and has_static


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Get project root directory.

    Returns:
        Path to project root (3 levels up from this file)
    """
    return Path(__file__).parent.parent.parent


def get_state_dir() -> Path:
    """Get state storage directory.

    Priority:
    1. DISTILLER_STATE_DIR environment variable
    2. ./var/lib/distiller (development)
    3. /var/lib/distiller (production)

    Returns:
        Path to state directory
    """
    if override := os.getenv("DISTILLER_STATE_DIR"):
        return Path(override)

    if _is_development():
        return get_project_root() / "var" / "lib" / "distiller"

    return Path("/var/lib/distiller")


def get_log_dir() -> Path:
    """Get log directory.

    Priority:
    1. DISTILLER_LOG_DIR environment variable
    2. ./var/log/distiller (development)
    3. /var/log/distiller (production)

    Returns:
        Path to log directory
    """
    if override := os.getenv("DISTILLER_LOG_DIR"):
        return Path(override)

    if _is_development():
        return get_project_root() / "var" / "log" / "distiller"

    return Path("/var/log/distiller")


def get_templates_dir() -> Path:
    """Get Jinja2 templates directory.

    Priority:
    1. DISTILLER_TEMPLATES_DIR environment variable
    2. ./templates (development)
    3. /usr/share/distiller-services/templates (production)

    Returns:
        Path to templates directory
    """
    if override := os.getenv("DISTILLER_TEMPLATES_DIR"):
        return Path(override)

    if _is_development():
        return get_project_root() / "templates"

    return Path("/usr/share/distiller-services/templates")


def get_static_dir() -> Path:
    """Get static files directory.

    Priority:
    1. DISTILLER_STATIC_DIR environment variable
    2. ./static (development)
    3. /usr/share/distiller-services/static (production)

    Returns:
        Path to static directory
    """
    if override := os.getenv("DISTILLER_STATIC_DIR"):
        return Path(override)

    if _is_development():
        return get_project_root() / "static"

    return Path("/usr/share/distiller-services/static")


def get_sdk_path() -> Path:
    """Get distiller-sdk source path.

    Priority:
    1. DISTILLER_SDK_PATH environment variable
    2. ../distiller-sdk/src (development, monorepo sibling)
    3. /opt/distiller-sdk/src (production)

    Returns:
        Path to SDK source directory
    """
    if override := os.getenv("DISTILLER_SDK_PATH"):
        return Path(override)

    # Try to find SDK in development environment (monorepo layout)
    if _is_development():
        project_root = get_project_root()
        sdk_path = project_root.parent / "distiller-sdk" / "src"
        if sdk_path.exists():
            return sdk_path

    # Fall back to production path
    return Path("/opt/distiller-sdk/src")


def get_device_env_path() -> Path:
    """Get device environment file path.

    Priority:
    1. DISTILLER_DEVICE_ENV_PATH environment variable
    2. /etc/pamir/device.env (production only, no dev fallback)

    Returns:
        Path to device.env file
    """
    if override := os.getenv("DISTILLER_DEVICE_ENV_PATH"):
        return Path(override)

    return Path("/etc/pamir/device.env")


def is_development_mode() -> bool:
    """Check if running in development mode.

    Returns:
        True if in development mode
    """
    return _is_development()
