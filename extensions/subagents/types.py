"""
types.py — Core data models for the subagents extension.

Mirrors the TypeScript pi-subagents-lite type system.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Thinking level ────────────────────────────────────────────────────────────

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

# ── Agent status ──────────────────────────────────────────────────────────────

AgentStatus = Literal[
    "queued", "running", "completed", "turn_limited", "aborted", "stopped", "error"
]

# ── System prompt mode ────────────────────────────────────────────────────────

SystemPromptMode = Literal["replace", "inherit", "custom"]

# ── Short ID length for display ───────────────────────────────────────────────

SHORT_ID_LENGTH = 8


# ═══════════════════════════════════════════════════════════════════════════════
# AgentConfig — defines an agent type (from defaults or .md files)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentConfig:
    """Unified agent configuration — mirrors TS AgentConfig interface."""
    name: str
    description: str
    system_prompt: str = ""
    display_name: str = ""
    model: str | None = None
    thinking_level: ThinkingLevel | None = None
    max_turns: int | None = None
    max_tokens: int | None = None

    # Tool visibility control
    tools: bool | list[str] | None = None  # true=all, list=whitelist, None=default
    exclude_tools: list[str] | None = None  # blacklist mode
    registered_tools: list[str] | None = None  # tools to register with the session

    # Extension/skill loading
    extensions: bool | list[str] | None = None
    exclude_extensions: list[str] | None = None
    skills: bool | list[str] | None = None
    preload_skills: list[str] | None = None

    # Metadata
    is_default: bool = False
    hidden: bool = False
    source: Literal["project", "global"] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# AgentRecord — full tracking state for a spawned agent
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LifetimeUsage:
    """Accumulated token/cost usage across turns."""
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cost: float = 0.0


@dataclass
class AgentLifecycle:
    """Lifecycle state: when the agent started, completed, current status."""
    status: AgentStatus = "running"
    started_at: float = 0.0
    completed_at: float | None = None


@dataclass
class AgentDisplayInfo:
    """Display-oriented fields: type name, description, output file."""
    type: str = ""
    description: str = ""
    output_file: str | None = None
    invocation: dict[str, Any] | None = None
    tool_call_id: str | None = None
    worktree_path: str | None = None
    worktree_label: str | None = None


@dataclass
class AgentExecutionState:
    """Execution internals: session, abort event, pending steers."""
    session: Any = None  # pi_agent.Agent instance
    abort_event: Any = None  # asyncio.Event
    promise: Any = None  # asyncio.Task
    pending_steers: list[str] | None = None
    output_log: Any = None  # AgentOutputLog


@dataclass
class AgentAccumulatedStats:
    """Accumulated statistics: usage, tool uses, turn count."""
    lifetime_usage: LifetimeUsage = field(default_factory=LifetimeUsage)
    tool_uses: int = 0
    turn_count: int = 1
    max_turns: int | None = None
    compaction_count: int = 0
    context_percent: float | None = None


@dataclass
class AgentRecord:
    """Full tracking record for a spawned agent."""
    id: str = ""
    result: str | None = None
    error: str | None = None
    lifecycle: AgentLifecycle = field(default_factory=AgentLifecycle)
    display: AgentDisplayInfo = field(default_factory=AgentDisplayInfo)
    execution: AgentExecutionState = field(default_factory=AgentExecutionState)
    stats: AgentAccumulatedStats = field(default_factory=AgentAccumulatedStats)


# ═══════════════════════════════════════════════════════════════════════════════
# Spawn configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SpawnConfig:
    """Coordinator-side spawn configuration."""
    description: str = ""
    model: Any = None  # pi_ai Model
    model_key: str | None = None
    max_turns: int | None = None
    max_tokens: int | None = None
    thinking_level: ThinkingLevel | None = None
    grace_turns: int = 6
    worktree_path: str | None = None
    worktree_label: str | None = None
    invocation: dict[str, Any] | None = None


@dataclass
class SpawnIntent(SpawnConfig):
    """Full spawn intent from the tool handler."""
    type: str = ""
    prompt: str = ""
    run_in_background: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Tool activity tracking
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ToolActivity:
    """Tool activity event: start/end of a tool invocation."""
    type: Literal["start", "end"]
    tool_name: str


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def is_terminal_status(status: AgentStatus) -> bool:
    """Check if an agent status is terminal (no longer running or queued)."""
    return status not in ("running", "queued")


def add_usage(into: LifetimeUsage, delta: LifetimeUsage) -> None:
    """Add a usage delta into a target accumulator (mutates target)."""
    into.input += delta.input
    into.output += delta.output
    into.cache_write += delta.cache_write
    into.cost += delta.cost


def get_lifetime_total(u: LifetimeUsage | None) -> float:
    """Sum of lifetime usage components, or 0 if None."""
    if u is None:
        return 0
    return u.input + u.output + u.cache_write + u.cost


def format_tokens(count: int, compact: bool = False) -> str:
    """Format a token count compactly: '12.3k', '1.2M', or raw number."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        if compact:
            return f"{round(count / 1_000)}k"
        return f"{count / 1_000:.1f}k"
    return str(count)


def get_status_note(status: AgentStatus) -> str:
    """Get a terminal status note for display."""
    notes: dict[AgentStatus, str] = {
        "completed": "",
        "turn_limited": "\n\n[Agent reached its turn limit and was stopped.]",
        "aborted": "\n\n[Agent was aborted.]",
        "stopped": "\n\n[Agent was stopped.]",
        "error": "\n\n[Agent encountered an error.]",
        "queued": "",
        "running": "",
    }
    return notes.get(status, "")
