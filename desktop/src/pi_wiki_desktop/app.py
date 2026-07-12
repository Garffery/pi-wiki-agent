"""FastAPI application for the wiki management desktop backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import router

# Global resource store — populated on startup, read by routes
_resource_store: dict[str, Any] = {}


def _get_resource_store() -> dict[str, Any]:
    return _resource_store


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Load resources on startup, clean up on shutdown."""
    from pi_wiki_agent.core.resource_loader import ResourceLoader, ResourceLoaderOptions

    loader = ResourceLoader(ResourceLoaderOptions(cwd=str(Path.cwd())))
    await loader.reload()

    # Convert loaded extensions to AgentTool instances + runner
    ext_result = loader.get_extensions()
    ext_tools: list[Any] = []
    ext_runner = None
    if ext_result.get("extensions"):
        from pi_wiki_agent.core.resource_loader import _build_extension_tools
        ext_tools, ext_runner = _build_extension_tools(ext_result["extensions"])

    # Store for routes to consume
    _resource_store["extension_tools"] = ext_tools
    _resource_store["extension_runner"] = ext_runner
    _resource_store["skills"] = loader.get_skills().get("skills", [])
    _resource_store["agents_files"] = loader.get_agents_files().get("agentsFiles", [])

    yield  # app runs here

    _resource_store.clear()


def create_app() -> FastAPI:
    app = FastAPI(title="pi-wiki-desktop", version="0.1.0", lifespan=_lifespan)

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
