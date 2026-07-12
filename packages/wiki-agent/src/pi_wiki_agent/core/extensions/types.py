"""Extension types — mirrors pi_coding_agent/core/extensions/types.py"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class PiManifest:
    extensions: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    name: str
    label: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    execute: Callable | None = None


@dataclass
class Extension:
    """A loaded extension with its handlers and tools."""
    resolved_path: str = ""
    handlers: dict[str, list[Callable]] = field(default_factory=dict)
    tools: dict[str, ToolDefinition] = field(default_factory=dict)
    commands: dict[str, Callable] = field(default_factory=dict)
    session_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtensionContext:
    """Context passed to extension event handlers."""
    cwd: str = ""
    session_id: str = ""
    extension_path: str = ""
    session_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallEvent:
    tool_call_id: str
    tool_name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultEvent:
    tool_call_id: str
    tool_name: str
    input: dict[str, Any] = field(default_factory=dict)
    content: list[dict] = field(default_factory=list)
    details: Any = None
    is_error: bool = False
