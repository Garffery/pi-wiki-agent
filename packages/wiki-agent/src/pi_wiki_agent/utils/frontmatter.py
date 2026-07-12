"""YAML frontmatter parser for wiki markdown pages."""

from __future__ import annotations

import re
from typing import Any

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown text. Returns (metadata, content_without_frontmatter)."""
    m = _FRONTMATTER_PATTERN.match(text)
    if not m:
        return {}, text

    try:
        import yaml
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        meta = _parse_simple_frontmatter(m.group(1))

    return meta, text[m.end():]


def _parse_simple_frontmatter(raw: str) -> dict[str, Any]:
    """Fallback parser for key: value pairs."""
    result: dict[str, Any] = {}
    for line in raw.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip("\"'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip("\"'") for v in val[1:-1].split(",")]
            result[key] = val
    return result
