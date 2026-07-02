"""
subagents — Multi-agent extension for pi-wiki-agent.

Port of pi-subagents-lite (TypeScript) to Python.
Registers Agent, StopAgent, and AgentStatus tools that allow the LLM
to spawn child agent sessions with isolated tool sets.

Entry point: extension_factory(api)
"""
from __future__ import annotations

import os
from typing import Any

from pi_coding_agent.core.extensions.types import ExtensionAPI

from .config import ConfigStore
from .coordinator import SpawnCoordinator
from .discovery import DEFAULT_AGENTS, merge_agents, scan_agent_files_in_dir
from .manager import AgentManager
from .registry import AgentTypeRegistry
from .tools import (
    build_agent_details,
    make_execute_agent,
    make_execute_agent_status,
    make_execute_stop_agent,
)

# ── Module-level state (closure-based, mirrors TS shell.ts) ───────────────────

_store: ConfigStore | None = None
_registry: AgentTypeRegistry | None = None
_manager: AgentManager | None = None
_coordinator: SpawnCoordinator | None = None
_parent_model: str = ""
_parent_cwd: str = ""
_initialized: bool = False
_api: Any = None  # ExtensionAPI reference, set by extension_factory

# Track subagent spawn depth to prevent re-initialization clobbering
_subagent_spawn_depth: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Agent tool parameter schema (matches TS Agent tool params)
# ═══════════════════════════════════════════════════════════════════════════════

AGENT_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The task for the agent to perform",
        },
        "description": {
            "type": "string",
            "description": "A short (3-5 word) description of the task",
        },
        "agent": {
            "type": "string",
            "description": "The type of specialized agent to use for this task",
        },
        "run_in_background": {
            "type": "boolean",
            "description": "Set to true to run this agent in the background",
        },
        "worktree_path": {
            "type": "string",
            "description": "Optional worktree path for isolation",
        },
    },
    "required": ["prompt"],
}

STOP_AGENT_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "agent_id": {
            "type": "string",
            "description": "The ID of the agent to stop",
        },
    },
    "required": ["agent_id"],
}

AGENT_STATUS_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {},
}


# ═══════════════════════════════════════════════════════════════════════════════
# Agent type descriptions (built for the tool description)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_agent_type_descriptions() -> str:
    """Build a description of available agent types for the tool description."""
    if not _registry:
        return ""
    types = _registry.get_available_types()
    if not types:
        return ""

    lines = ["Available agent types and the tools they have access to:"]
    for t in types:
        config = _registry.get_config(t)
        if config:
            tools_str = ", ".join(config.registered_tools or _registry.get_tool_names_for_type(t))
            hidden = " (hidden)" if config.hidden else ""
            lines.append(f"- {t}{hidden}: {config.description} (Tools: {tools_str})")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Event handlers
# ═══════════════════════════════════════════════════════════════════════════════

async def _on_session_start(ctx: Any, event: Any = None) -> None:
    """Initialize subagent system on session start."""
    global _store, _registry, _manager, _coordinator, _initialized
    global _parent_model, _parent_cwd

    if _subagent_spawn_depth > 0:
        return

    # Initialize store
    if _store is None:
        _store = ConfigStore()
    _store.reload()

    # Track parent context
    _parent_cwd = getattr(ctx, "cwd", os.getcwd())
    model = getattr(ctx, "model", None)
    if model:
        provider = getattr(model, "provider", "")
        model_id = getattr(model, "id", "")
        _parent_model = f"{provider}/{model_id}" if provider and model_id else ""

    # Initialize registry and scan for agent definitions
    if _registry is None:
        _registry = AgentTypeRegistry()

    home_dir = os.path.expanduser("~")
    user_agent_dir = os.path.join(home_dir, ".pi", "agent", "agents")
    project_agent_dir = os.path.join(_parent_cwd, ".pi", "agents")
    _registry.set_scan_dirs(user_agent_dir, project_agent_dir)

    # Scan and merge agents
    user_agents = scan_agent_files_in_dir(user_agent_dir, "user")
    project_agents = scan_agent_files_in_dir(project_agent_dir, "project")

    disable_defaults = _store.config.agent.disable_default_agents
    defaults: dict[str, Any] = {} if disable_defaults else DEFAULT_AGENTS
    merged = merge_agents(defaults, user_agents, project_agents)
    _registry.register(merged, disable_defaults=disable_defaults)

    # Initialize manager and coordinator
    concurrency_config = {
        "default": _store.config.concurrency.default,
        "providers": _store.config.concurrency.providers,
        "models": _store.config.concurrency.models,
    }

    _manager = AgentManager(
        concurrency_config=concurrency_config,
        buffer_size=_store.config.agent.output_thinking_buffer_size,
    )

    _coordinator = SpawnCoordinator(_manager, api=_api)

    # Wire manager completion → coordinator
    _manager.set_on_complete(_coordinator.on_agent_complete)

    _initialized = True


async def _on_session_shutdown(ctx: Any, event: Any = None) -> None:
    """Clean up subagent system on session shutdown."""
    global _manager, _coordinator, _store
    if _coordinator:
        _coordinator.dispose()
        _coordinator = None
    if _store:
        _store.dispose()
    if _manager:
        await _manager.dispose()
        _manager = None


async def _on_tool_call(ctx: Any, event: Any = None) -> dict | None:
    """Inject model into Agent tool calls before execution."""
    # event is a dict: {"type": "tool_call", "tool_name": ..., "input": ...}
    tool_name = event.get("tool_name", "") if isinstance(event, dict) else getattr(event, "tool_name", "")
    if tool_name not in ("agent", "Agent"):
        return None

    params = event.get("input", {}) if isinstance(event, dict) else getattr(event, "input", {})
    if not isinstance(params, dict):
        return None

    subagent_type = params.get("agent") or "general-purpose"
    config = _registry.get_config(subagent_type) if _registry else None

    if _store:
        model_str = _store.model_for(subagent_type, _parent_model, config)
        if model_str:
            params["model"] = model_str

    # Inject thinking from agent config if not explicitly passed
    if "thinking" not in params and config and config.thinking_level:
        params["thinking"] = config.thinking_level

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Extension entry point
# ═══════════════════════════════════════════════════════════════════════════════

def extension_factory(api: ExtensionAPI) -> None:
    """
    Register the subagents extension.

    Tools are registered immediately (before session creation) so the
    SDK collects them. The execute functions use lazy lookup via module
    globals, which are populated when session_start fires.
    """
    global _store, _registry, _api

    _api = api

    if _store is None:
        _store = ConfigStore()
    if _registry is None:
        _registry = AgentTypeRegistry()

    # ── Event handlers ────────────────────────────────────────────────────
    api.on("session_shutdown", _on_session_shutdown)
    api.on("tool_call", _on_tool_call)

    # ── Lazy helpers (coordinator/manager populated at session_start) ─────
    def _get_parent_model() -> str:
        return _parent_model

    def _get_parent_cwd() -> str:
        return _parent_cwd

    # ── Register tools NOW (before session creation) with lazy executors ──

    async def _agent_execute(params):
        if not _coordinator or not _manager or not _store or not _registry:
            from .tools import _error
            return _error("Subagent system not initialized. Wait for session_start.")
        executor = make_execute_agent(
            _coordinator, _registry, _store,
            _get_parent_model, _get_parent_cwd,
        )
        return await executor("", params, None, None, None)

    async def _stop_agent_execute(params):
        if not _manager:
            from .tools import _error
            return _error("Subagent system not initialized.")
        executor = make_execute_stop_agent(_manager)
        return await executor("", params, None, None, None)

    async def _agent_status_execute(params):
        if not _coordinator or not _manager:
            from .tools import _error
            return _error("Subagent system not initialized.")
        executor = make_execute_agent_status(_coordinator, _manager)
        return await executor("", params, None, None, None)

    api.register_tool(
        name="agent",
        label="Agent",
        description=(
            "Launch a new agent to handle complex, multi-step tasks. "
            "Available agent types: general-purpose (all tools), "
            "Explore (read-only: read/bash/grep/find). "
            "Use run_in_background=true for parallel work."
        ),
        parameters=AGENT_TOOL_PARAMETERS,
        execute=_agent_execute,
        prompt_snippet="Launch a sub-agent to handle a complex task",
        prompt_guidelines=[
            "Use for complex multi-step tasks that benefit from isolation",
            "Specify the agent type based on the task requirements",
            "Prefer foreground execution for results you need immediately",
            "Use background execution for independent parallel work",
        ],
    )

    api.register_tool(
        name="stop_agent",
        label="StopAgent",
        description="Stop a running background agent by its ID",
        parameters=STOP_AGENT_TOOL_PARAMETERS,
        execute=_stop_agent_execute,
    )

    api.register_tool(
        name="agent_status",
        label="AgentStatus",
        description="Check the status of all running and completed agents",
        parameters=AGENT_STATUS_TOOL_PARAMETERS,
        execute=_agent_status_execute,
    )

    # ── session_start: initialize the actual system ────────────────────────
    async def _session_start_full(ctx: Any, event: Any = None) -> None:
        await _on_session_start(ctx, event)

    api.on("session_start", _session_start_full)

    # Register /agents slash command
    def _agents_command(args: str, ctx: Any) -> None:
        """List running and completed agents."""
        if not _manager:
            print("No sub-agents active. Agent system not initialized.")
            return

        records = _manager.list_agents()
        if not records:
            print("No agents have been spawned in this session.")
            return

        print(f"\n{'='*60}")
        print(f"  Sub-Agents ({len(records)} total)")
        print(f"{'='*60}")
        for r in records:
            short_id = r.id[:SHORT_ID_LENGTH]
            status = r.lifecycle.status.upper()
            print(f"  [{status}] {short_id} — {r.display.type}: {r.display.description[:50]}")
        print()

    api.register_command(
        name="agents",
        description="List and manage sub-agents",
        handler=_agents_command,
    )
