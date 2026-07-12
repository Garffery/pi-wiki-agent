"""Git URL parsing utility."""

from __future__ import annotations

import re

_GIT_URL_RE = re.compile(r"(?:https://|git@)([^/:]+)[/:](.+?)(?:\.git)?$")


def parse_git_url(url: str) -> tuple[str, str] | None:
    """Parse a git URL into (owner, repo). Returns None if not a git URL."""
    m = _GIT_URL_RE.match(url.strip())
    if m:
        return m.group(1), m.group(2)
    return None
