"""Resource diagnostic types for wiki-agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ResourceCollision:
    resource_type: Literal["extension", "skill", "prompt"]
    name: str
    winner_path: str
    loser_path: str


@dataclass
class ResourceDiagnostic:
    type: Literal["warning", "error", "collision"]
    message: str
    path: str | None = None
    collision: ResourceCollision | None = None
