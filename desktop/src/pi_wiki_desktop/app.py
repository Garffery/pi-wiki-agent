"""FastAPI application for the wiki management desktop backend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="pi-wiki-desktop", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
