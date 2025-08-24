"""
State management with event-driven updates.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """WiFi connection states."""

    AP_MODE = "AP_MODE"
    SWITCHING = "SWITCHING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    DISCONNECTED = "DISCONNECTED"


class NetworkInfo(BaseModel):
    """Network connection information."""

    ssid: str | None = None
    ip_address: str | None = None
    signal_strength: int | None = None
    security: str | None = None
    connected_at: datetime | None = None


class SessionInfo(BaseModel):
    """User session tracking."""

    session_id: str
    created_at: datetime
    last_seen: datetime


class SystemState(BaseModel):
    """Complete system state."""

    connection_state: ConnectionState = ConnectionState.AP_MODE
    network_info: NetworkInfo = Field(default_factory=NetworkInfo)
    tunnel_url: str | None = None
    ap_password: str | None = None  # Dynamic AP password for current session
    error_message: str | None = None
    retry_count: int = 0
    sessions: dict[str, SessionInfo] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.now)


class StateManager:
    """
    Manages system state with event-driven updates.

    Features:
    - In-memory state with optional persistence
    - Async event callbacks for state changes
    - Session tracking across network transitions
    """

    def __init__(self, state_file: Path | None = None):
        self.state = SystemState()
        self.state_file = state_file
        self._callbacks: dict[str, list[Any]] = {}
        self._lock = asyncio.Lock()

        # Load existing state if available
        if state_file and state_file.exists():
            self._load_state()
            # Clear tunnel_url to prevent showing stale URLs on restart
            self.state.tunnel_url = None

    def _load_state(self) -> None:
        """Load state from file."""
        try:
            if not self.state_file:
                return
            with open(self.state_file) as f:
                data = json.load(f)
                # Convert datetime strings back to datetime objects
                if "updated_at" in data:
                    data["updated_at"] = datetime.fromisoformat(data["updated_at"])
                if "network_info" in data and "connected_at" in data["network_info"]:
                    if data["network_info"]["connected_at"]:
                        data["network_info"]["connected_at"] = datetime.fromisoformat(
                            data["network_info"]["connected_at"]
                        )
                # Recreate sessions
                if "sessions" in data:
                    for _session_id, session_data in data["sessions"].items():
                        session_data["created_at"] = datetime.fromisoformat(
                            session_data["created_at"]
                        )
                        session_data["last_seen"] = datetime.fromisoformat(
                            session_data["last_seen"]
                        )

                self.state = SystemState(**data)
                logger.info(f"Loaded state from {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    async def _save_state(self) -> None:
        """Save state to file."""
        if not self.state_file:
            return

        try:
            # Convert to JSON-serializable format
            data = self.state.model_dump(mode="json")

            # Convert datetime objects to ISO format strings
            if "updated_at" in data:
                data["updated_at"] = self.state.updated_at.isoformat()
            if "network_info" in data and self.state.network_info.connected_at:
                data["network_info"]["connected_at"] = (
                    self.state.network_info.connected_at.isoformat()
                )

            # Convert session datetimes
            for session_id, session in self.state.sessions.items():
                data["sessions"][session_id]["created_at"] = session.created_at.isoformat()
                data["sessions"][session_id]["last_seen"] = session.last_seen.isoformat()

            # Write atomically
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            temp_file.rename(self.state_file)

        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def update_state(
        self,
        connection_state: ConnectionState | None = None,
        network_info: NetworkInfo | None = None,
        tunnel_url: str | None = None,
        ap_password: str | None = None,
        error_message: str | None = None,
        increment_retry: bool = False,
        reset_retry: bool = False,
    ) -> None:
        """Update system state and trigger callbacks."""
        async with self._lock:
            old_state = self.state.connection_state
            old_tunnel_url = self.state.tunnel_url

            # Update fields
            if connection_state is not None:
                self.state.connection_state = connection_state

            if network_info is not None:
                self.state.network_info = network_info

            if tunnel_url is not None:
                self.state.tunnel_url = tunnel_url

            if ap_password is not None:
                self.state.ap_password = ap_password

            if error_message is not None:
                self.state.error_message = error_message
            elif connection_state == ConnectionState.CONNECTED:
                self.state.error_message = None

            if increment_retry:
                self.state.retry_count += 1
            elif reset_retry:
                self.state.retry_count = 0

            self.state.updated_at = datetime.now()

            # Save state
            await self._save_state()

            # Trigger callbacks if state or tunnel_url changed
            if old_state != self.state.connection_state or old_tunnel_url != self.state.tunnel_url:
                await self._trigger_callbacks(
                    "state_change", old_state, self.state.connection_state
                )

    async def add_session(self, session: SessionInfo) -> None:
        """Add or update a session."""
        async with self._lock:
            self.state.sessions[session.session_id] = session
            await self._save_state()

    async def update_session_activity(self, session_id: str) -> None:
        """Update last seen time for a session."""
        async with self._lock:
            if session_id in self.state.sessions:
                self.state.sessions[session_id].last_seen = datetime.now()
                await self._save_state()

    async def remove_stale_sessions(self, max_age_seconds: int = 3600) -> None:
        """Remove sessions that haven't been seen recently."""
        async with self._lock:
            now = datetime.now()
            stale_sessions = []

            for session_id, session in self.state.sessions.items():
                age = (now - session.last_seen).total_seconds()
                if age > max_age_seconds:
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                del self.state.sessions[session_id]
                logger.debug(f"Removed stale session: {session_id}")

            if stale_sessions:
                await self._save_state()

    def on_state_change(self, callback: Any) -> None:
        """Register a callback for state changes."""
        if "state_change" not in self._callbacks:
            self._callbacks["state_change"] = []
        self._callbacks["state_change"].append(callback)

    async def _trigger_callbacks(self, event: str, *args, **kwargs) -> None:
        """Trigger registered callbacks for an event."""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(*args, **kwargs)
                    else:
                        callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Callback error for {event}: {e}")

    def get_state(self) -> SystemState:
        """Get current state."""
        return self.state

    def is_connected(self) -> bool:
        """Check if currently connected to a network."""
        return self.state.connection_state == ConnectionState.CONNECTED

    def is_in_ap_mode(self) -> bool:
        """Check if currently in AP mode."""
        return self.state.connection_state == ConnectionState.AP_MODE
