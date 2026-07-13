"""Shared resource store — all resources loaded once at module import time.

Usage::

    from .resources import get_resource_store

    store = get_resource_store()
    # store["skills"], store["extension_tools"], store["extension_runner"]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_resource_store: dict[str, Any] = {}


def _init_resources() -> None:
    """Load all resources (skills + extensions + context files) on module import."""
    from pi_wiki_agent.core.resource_loader import (
        ResourceLoader,
        ResourceLoaderOptions,
        _build_extension_tools,
    )

    cwd = str(Path.cwd())
    loader = ResourceLoader(ResourceLoaderOptions(cwd=cwd))
    loader.reload()

    ext_tools: list[Any] = []
    ext_runner = None
    extensions = loader.get_extensions().get("extensions", [])
    if extensions:
        ext_tools, ext_runner = _build_extension_tools(extensions)

    _resource_store["skills"] = loader.get_skills().get("skills", [])
    _resource_store["extension_tools"] = ext_tools
    _resource_store["extension_runner"] = ext_runner
    _resource_store["agents_files"] = loader.get_agents_files().get("agentsFiles", [])


def get_resource_store() -> dict[str, Any]:
    """Get the module-level resource store (all resources ready)."""
    return _resource_store


# ── Init on import ────────────────────────────────────────────────────────────
_init_resources()
