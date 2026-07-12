"""Configuration paths for pi-wiki-agent."""

from __future__ import annotations

import os
from importlib.metadata import version as _pkg_version
from pathlib import Path

APP_NAME: str = "pi-wiki"
CONFIG_DIR_NAME: str = ".pi"

try:
    VERSION: str = _pkg_version("pi-wiki-core")
except Exception:
    VERSION = "0.1.0"


def get_agent_dir() -> str:
    """Get the wiki agent config directory (~/.pi/wiki-agent/)."""
    return os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME, "wiki-agent")


def get_settings_path() -> str:
    return os.path.join(get_agent_dir(), "settings.json")


def find_project_root(cwd: str | None = None) -> str:
    """Find the project root by looking for .wiki directory or VCS markers."""
    current = Path(cwd or os.getcwd())
    markers = {".wiki", ".git", "pyproject.toml"}
    while True:
        for marker in markers:
            if (current / marker).exists():
                return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return cwd or os.getcwd()
