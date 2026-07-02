"""WebSocket connection manager — tracks connections per session."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from ..serialization import safe_json_serialize

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by session_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = []
            self._connections[session_id].append(ws)
        logger.info(f"WS connected to session {session_id} (total: {len(self._connections.get(session_id, []))})")

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].remove(ws)
                if not self._connections[session_id]:
                    del self._connections[session_id]

    async def broadcast(self, session_id: str, event: dict[str, Any]) -> None:
        """Send an event to all WebSocket connections for a session."""
        connections = self._connections.get(session_id, [])
        if not connections:
            return

        message = safe_json_serialize(event)
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(session_id, ws)
