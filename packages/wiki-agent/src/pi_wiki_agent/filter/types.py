"""Filter data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilterRule(BaseModel):
    """A single filter rule.

    - type=path:    pattern is a glob/fnmatch expression against file paths.
    - type=message: pattern is a regex against the commit message.
    """

    type: str = Field(..., pattern=r"^(path|message)$")
    pattern: str
    description: str = ""


class FilterConfig(BaseModel):
    """Per-project filter configuration stored in .wiki/filter.json."""

    rules: list[FilterRule] = []
    enabled: bool = True
