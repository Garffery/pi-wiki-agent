"""Binary tool manager for wiki-agent (rg, fd)."""

from __future__ import annotations

import os


def find_tool(name: str) -> str | None:
    """Find a binary tool in PATH."""
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(path_dir, name)
        if os.path.isfile(full):
            return full
        ext_path = full + (".exe" if os.name == "nt" else "")
        if os.path.isfile(ext_path):
            return ext_path
    return None
