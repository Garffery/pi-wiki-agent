"""FastAPI application for the wiki management desktop backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.v1.router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pi_coding_agent.core.auth_storage import AuthStorage
    from .wiki_model_registry import WikiModelRegistry
    app.state.model_registry = WikiModelRegistry(auth_storage=AuthStorage())

    # Start cron scheduler
    from pi_wiki_agent.cron import scheduler
    scheduler.start()
    _register_default_jobs()

    yield

    scheduler.shutdown()
    app.state.model_registry = None


def _register_default_jobs() -> None:
    """Register built-in scheduled jobs if configured."""
    import os
    from pi_wiki_agent.cron import scheduler

    # These are optional defaults — can be configured via env or config file later
    # Example: os.environ.get("PI_WIKI_CRON_QUALITY_CHECK", "") == "1"
    # For now, no jobs are auto-registered — use the API to add them
    pass


def create_app() -> FastAPI:
    app = FastAPI(title="pi-wiki-desktop", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Disable caching for frontend files during development ─────────────
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class NoCacheStaticMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            # Add no-cache for all responses
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            return response

    app.add_middleware(NoCacheStaticMiddleware)

    app.include_router(router)

    # Mount frontend static files
    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()


def main():
    """Entry point for `pi-wiki-desktop` CLI."""
    import os
    import uvicorn
    reload = os.environ.get("PI_WIKI_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("pi_wiki_desktop.app:app", host="127.0.0.1", port=8899, reload=reload)


if __name__ == "__main__":
    main()
