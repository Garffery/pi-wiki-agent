"""FastAPI application entry point for Pi Desktop backend."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .config import get_port
from .session_pool import SessionPool
from .ws.handlers import session_stream
from .ws.manager import ConnectionManager
from .routes import chat, commands, health, models, sessions, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create session pool and WS manager. Shutdown: cleanup."""
    pool = SessionPool()
    ws_manager = ConnectionManager()
    pool.set_ws_manager(ws_manager)
    app.state.session_pool = pool
    app.state.ws_manager = ws_manager
    logger.info("Backend started")
    yield
    # Cleanup all sessions
    for sid in list(pool._sessions.keys()):
        try:
            await pool.delete_session(sid)
        except Exception:
            pass
    logger.info("Backend shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pi Desktop Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins in dev (localhost-only in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST routes
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(commands.router)
    app.include_router(models.router)
    app.include_router(settings.router)

    # WebSocket endpoint
    @app.websocket("/api/sessions/{session_id}/stream")
    async def ws_session_stream(ws: WebSocket, session_id: str):
        pool = app.state.session_pool
        ws_manager = app.state.ws_manager
        await session_stream(ws, session_id, ws_manager, pool)

    return app


def main():
    """Entry point — starts uvicorn on a free port, signals port via stdout."""
    port = get_port()
    app = create_app()

    # Signal port to parent process (Electron) via stdout JSON line
    print(json.dumps({"port": port}), flush=True)

    import uvicorn
    import socket
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    # Create socket with SO_REUSEADDR to avoid TIME_WAIT binding errors
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
