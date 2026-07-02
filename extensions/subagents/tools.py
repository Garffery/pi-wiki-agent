"""
tools.py — Agent, StopAgent, AgentStatus tool execution handlers.

These are the execute callbacks registered for the subagent tools.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

from pi_ai import get_model

from .config import ConfigStore
from .coordinator import SpawnCoordinator
from .manager import AgentManager
from .models import resolve_model
from .registry import AgentTypeRegistry
from .runner import _build_tools, _build_system_prompt, run_subagent
from .types import SHORT_ID_LENGTH, AgentRecord, get_status_note


# ═══════════════════════════════════════════════════════════════════════════════
# Tool result helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _success(text: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "details": details or {}}


def _error(text: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True, "details": details or {}}


# ═══════════════════════════════════════════════════════════════════════════════
# build_agent_details
# ═══════════════════════════════════════════════════════════════════════════════

def build_agent_details(
    record: AgentRecord,
    include_stats: bool = False,
    include_status: bool = False,
) -> dict[str, Any]:
    """Build a details dict from an AgentRecord."""
    details: dict[str, Any] = {
        "type": record.display.type,
        "description": record.display.description,
    }

    if record.display.worktree_path:
        details["worktreePath"] = record.display.worktree_path

    if include_status:
        details["status"] = record.lifecycle.status
        details["outputFile"] = record.display.output_file

    if include_stats:
        elapsed_ms = 0.0
        if record.lifecycle.completed_at:
            elapsed_ms = (record.lifecycle.completed_at - record.lifecycle.started_at) * 1000

        details.update({
            "turnCount": record.stats.turn_count,
            "maxTurns": record.stats.max_turns,
            "toolUses": record.stats.tool_uses,
            "input": record.stats.lifetime_usage.input,
            "output": record.stats.lifetime_usage.output,
            "contextPercent": record.stats.context_percent,
            "durationMs": int(elapsed_ms),
            "compactions": record.stats.compaction_count,
            "cost": record.stats.lifetime_usage.cost,
        })

    return details


# ═══════════════════════════════════════════════════════════════════════════════
# Agent tool executor factory
# ═══════════════════════════════════════════════════════════════════════════════

def make_execute_agent(
    coordinator: SpawnCoordinator,
    registry: AgentTypeRegistry,
    store: ConfigStore,
    get_parent_model: Callable[[], str],
    get_cwd: Callable[[], str],
) -> Callable[..., Any]:
    """Create the execute function for the Agent tool."""

    async def execute_agent(
        tool_call_id: str,
        params: dict[str, Any],
        cancel_event: asyncio.Event | None,
        on_update: Any,
        ctx: Any,
    ) -> dict[str, Any]:
        # Resolve agent type
        type_name = params.get("agent") or params.get("subagent_type") or "general-purpose"
        resolved_type = registry.resolve(type_name)
        if not resolved_type:
            return _error(f"Unknown agent type: {type_name}")

        agent_config = registry.get_config(resolved_type)
        prompt = params.get("prompt", "")
        description = params.get("description") or (
            prompt.split("\n")[0][:80] if prompt else prompt[:80]
        )
        run_in_background = params.get("run_in_background", False) or store.config.agent.force_background

        # Security: validate agent name
        if ".." in type_name or "/" in type_name or "\\" in type_name:
            return _error(f"Invalid agent type name: {type_name}")

        # Resolve model
        parent_model = get_parent_model()
        model_str = resolve_model(
            subagent_type=resolved_type,
            agent_config=agent_config,
            config=store.config,
            parent_model_id=parent_model,
            session_overrides=store.session_overrides,
        )

        # Parse model string to Model object
        try:
            model = _parse_model_string(model_str)
        except Exception:
            model = _parse_model_string(parent_model)

        thinking_level = params.get("thinking") or (
            agent_config.thinking_level if agent_config else None
        ) or "off"

        # Resolve max_turns
        max_turns = params.get("max_turns")
        if max_turns is None and agent_config:
            max_turns = agent_config.max_turns
        if max_turns is None:
            max_turns = store.config.agent.default_max_turns

        cwd = get_cwd()

        # Build tools for the sub-agent
        tool_names = registry.get_tool_names_for_type(resolved_type)
        tools = _build_tools(cwd, tool_names)

        # Create runner factory
        async def runner_factory(record: AgentRecord) -> str:
            return await run_subagent(
                agent_config=agent_config,
                prompt=prompt,
                model=model,
                tools=tools,
                thinking_level=thinking_level,  # type: ignore[arg-type]
                max_turns=max_turns,
                cwd=cwd,
                record=record,
            )

        # Spawn via coordinator
        result = await coordinator.spawn(
            type_name=resolved_type,
            prompt=prompt,
            description=description,
            model_key=_model_key(model),
            max_turns=max_turns,
            thinking_level=thinking_level,
            grace_turns=store.config.agent.grace_turns,
            invocation={"model_name": getattr(model, "id", model_str)},
            run_in_background=run_in_background,
            runner_factory=runner_factory,
        )

        agent_id = result["agent_id"]
        record = result["record"]

        if not record:
            return _error("Failed to create agent record")

        if run_in_background:
            label = "Agent queued" if record.lifecycle.status == "queued" else "Agent running"
            suffix = (
                f"A notification will arrive when done. "
                f"Do not poll, check status or duplicate the delegated work.\n\n"
                f"Agent ID: {agent_id}"
            )
            return _success(f"[{label}] {suffix}", build_agent_details(record))

        # Foreground: result is ready
        details = build_agent_details(record, include_stats=True)

        if record.lifecycle.status == "error":
            return _error(f"Agent failed: {record.error or 'unknown error'}", details)

        status_note = get_status_note(record.lifecycle.status)
        return _success((record.result or "") + status_note, details)

    return execute_agent


# ═══════════════════════════════════════════════════════════════════════════════
# StopAgent tool executor factory
# ═══════════════════════════════════════════════════════════════════════════════

def make_execute_stop_agent(manager: AgentManager) -> Callable[..., Any]:
    """Create the execute function for the StopAgent tool."""

    async def execute_stop_agent(
        tool_call_id: str,
        params: dict[str, Any],
        cancel_event: asyncio.Event | None,
        on_update: Any,
        ctx: Any,
    ) -> dict[str, Any]:
        agent_id = params.get("agent_id", "")

        if not agent_id:
            return _error("agent_id is required")

        record = manager.get_record(agent_id)
        if not record:
            running = _format_running_agents(manager)
            return _error(f"Agent {agent_id} not found. Running agents: {running}")

        if record.lifecycle.status not in ("running", "queued"):
            running = _format_running_agents(manager)
            return _success(
                f"Agent {agent_id} is already {record.lifecycle.status}. "
                f"Running agents: {running}"
            )

        if manager.abort(agent_id):
            return _success(f"Stopped agent {agent_id[:SHORT_ID_LENGTH]}")

        return _error(f"Failed to stop agent {agent_id}")

    return execute_stop_agent


# ═══════════════════════════════════════════════════════════════════════════════
# AgentStatus tool executor factory
# ═══════════════════════════════════════════════════════════════════════════════

def make_execute_agent_status(
    coordinator: SpawnCoordinator,
    manager: AgentManager,
) -> Callable[..., Any]:
    """Create the execute function for the AgentStatus tool."""

    async def execute_agent_status(
        tool_call_id: str,
        params: dict[str, Any],
        cancel_event: asyncio.Event | None,
        on_update: Any,
        ctx: Any,
    ) -> dict[str, Any]:
        records = manager.list_agents()
        if not records:
            return _success("No agents running or completed in this session.")

        lines = []
        for r in records:
            short_id = r.id[:SHORT_ID_LENGTH]
            elapsed = ""
            if r.lifecycle.completed_at:
                elapsed_ms = (r.lifecycle.completed_at - r.lifecycle.started_at) * 1000
                elapsed = f" ({elapsed_ms / 1000:.1f}s)"
            lines.append(
                f"- {short_id}: [{r.lifecycle.status}] {r.display.type} — "
                f"{r.display.description[:60]}{elapsed}"
            )

        return _success("\n".join(lines))

    return execute_agent_status


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _format_running_agents(manager: AgentManager) -> str:
    """Format a compact list of running/queued agents."""
    agents = [
        r for r in manager.list_agents()
        if r.lifecycle.status in ("running", "queued")
    ]
    if not agents:
        return "none"
    return ", ".join(
        f"{a.id[:SHORT_ID_LENGTH]} ({a.display.type})" for a in agents
    )


def _model_key(model: Any) -> str | None:
    """Extract 'provider/modelId' key from a Model object."""
    provider = getattr(model, "provider", None)
    model_id = getattr(model, "id", None)
    if provider and model_id:
        return f"{provider}/{model_id}"
    return None


def _parse_model_string(model_str: str) -> Any:
    """Parse a 'provider/modelId' string into a Model object."""
    if not model_str or "/" not in model_str:
        return None
    provider, model_id = model_str.split("/", 1)
    # Try pi_ai.get_model first, then fall back to ModelRegistry
    m = get_model(provider, model_id)
    if m is not None:
        return m
    try:
        from pi_coding_agent.core.model_registry import ModelRegistry
        registry = ModelRegistry()
        return registry.find(provider, model_id)
    except Exception:
        return None
