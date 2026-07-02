"""
logging.py — Human-readable output logging for agent transcripts.

Path: ~/.pi/agent/subagents/<agent_id>.log
Append-only, human-readable, supports `tail -f`.
Lines: [USER], [TOOL], [ASSISTANT], [DONE] with ISO timestamps.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .types import format_tokens


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _output_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".pi", "agent", "subagents")


def create_output_path(agent_id: str) -> str:
    """Create the output file path for an agent. Ensures parent directory exists."""
    d = _output_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{agent_id}.log")


def write_initial_entry(path: str, prompt: str) -> None:
    """Write the initial [USER] prompt entry to the output file."""
    line = f"{_timestamp()} [USER] {prompt}\n"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _safe_append(path: str, content: str) -> None:
    """Best-effort append — silently ignores write errors."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        pass


def append_tool_call(path: str, tool_name: str, args: dict[str, Any] | None = None) -> None:
    """Append a [TOOL] line to the output file."""
    args_str = ""
    if args:
        # Summarize common args
        parts = []
        for k, v in args.items():
            if isinstance(v, str):
                v_str = v[:80] + "..." if len(v) > 80 else v
                parts.append(f"{k}={v_str}")
        if parts:
            args_str = " " + ", ".join(parts[:3])
    _safe_append(path, f"{_timestamp()} [TOOL] {tool_name}{args_str}\n")


def append_tool_result(path: str, tool_name: str, text: str) -> None:
    """Append a [TOOL_RESULT] line, truncating if too long."""
    if len(text) > 500:
        _safe_append(path, f"{_timestamp()} [TOOL_RESULT] {tool_name}: {len(text)} chars\n")
    elif text.strip():
        for line in text.split("\n"):
            if line.strip():
                _safe_append(path, f"{_timestamp()} [TOOL_RESULT] {line}\n")


def append_assistant_text(path: str, text: str) -> None:
    """Append [ASSISTANT] text lines."""
    for line in text.split("\n"):
        if line.strip():
            _safe_append(path, f"{_timestamp()} [ASSISTANT] {line}\n")


def finalize_output(
    path: str,
    turn_count: int = 0,
    tool_use_count: int = 0,
    total_tokens: int = 0,
    cost: float = 0.0,
) -> None:
    """Write the [DONE] summary line with final stats."""
    tokens_str = format_tokens(total_tokens)
    cost_str = f"${cost:.3f}"
    line = f"{_timestamp()} [DONE] {turn_count} turns, {tool_use_count} tool uses, {tokens_str}, {cost_str}\n"
    _safe_append(path, line)


class AgentOutputLog:
    """Lifecycle wrapper for per-agent output streaming."""

    def __init__(self, agent_id: str, prompt: str) -> None:
        self.path = create_output_path(agent_id)
        write_initial_entry(self.path, prompt)

    def log_tool_call(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        append_tool_call(self.path, tool_name, args)

    def log_tool_result(self, tool_name: str, text: str) -> None:
        append_tool_result(self.path, tool_name, text)

    def log_assistant_text(self, text: str) -> None:
        append_assistant_text(self.path, text)

    def finalize(
        self,
        turn_count: int = 0,
        tool_use_count: int = 0,
        total_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        finalize_output(self.path, turn_count, tool_use_count, total_tokens, cost)
