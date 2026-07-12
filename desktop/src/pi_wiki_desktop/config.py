"""Project configuration management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".pi-wiki-agent"
CONFIG_FILE = CONFIG_DIR / "projects.json"


def load_projects() -> dict[str, dict[str, str]]:
    """Load configured wiki projects. Returns {name: {path, vcs}}. """
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}


def save_projects(projects: dict[str, dict[str, str]]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(projects, indent=2, ensure_ascii=False), "utf-8")


def add_project(name: str, path: str) -> None:
    projects = load_projects()
    vcs_type = "git" if (Path(path) / ".git").exists() else "svn" if (Path(path) / ".svn").exists() else "unknown"
    projects[name] = {"path": path, "vcs": vcs_type}
    save_projects(projects)


def remove_project(name: str) -> bool:
    projects = load_projects()
    if name not in projects:
        return False
    del projects[name]
    save_projects(projects)
    return True


