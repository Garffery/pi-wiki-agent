"""WebSocket route handlers."""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


async def session_stream(ws: WebSocket, session_id: str, manager, pool) -> None:
    """WebSocket endpoint for streaming session events."""
    session = await pool.get_session(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    await manager.connect(session_id, ws)

    try:
        # Send current state snapshot on connect
        context_usage = session.get_context_usage()
        if context_usage:
            await ws.send_json({"type": "context_usage", **context_usage})

        # Keep connection alive, listen for client messages (abort, steer, etc.)
        while True:
            data = await ws.receive_json()
            action = data.get("action", "")
            if action == "abort":
                await pool.abort_session(session_id)
            elif action == "steer":
                msg = data.get("message", "")
                if msg:
                    session.steer(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error for session {session_id}: {e}")
    finally:
        await manager.disconnect(session_id, ws)
