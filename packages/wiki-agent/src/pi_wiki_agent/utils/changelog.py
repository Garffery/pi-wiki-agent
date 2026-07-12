"""CHANGELOG.md parsing utility."""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r"##\s*\[?(\d+\.\d+\.\d+)\]?")


def parse_changelog(text: str) -> list[dict]:
    """Parse a CHANGELOG.md into a list of version entries."""
    entries: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = _VERSION_RE.match(line)
        if m:
            if current:
                entries.append(current)
            current = {"version": m.group(1), "changes": []}
        elif current and line.strip().startswith("-"):
            current["changes"].append(line.strip("- ").strip())
    if current:
        entries.append(current)
    return entries
