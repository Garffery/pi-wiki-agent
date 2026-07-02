"""
registry.py — Unified agent type registry.

Merges embedded default agents with user-defined agents from .pi/agents/*.md.
User agents override defaults with the same name.
"""
from __future__ import annotations

from typing import Any

from .discovery import DEFAULT_AGENTS, merge_agents, scan_agent_files_in_dir
from .types import AgentConfig

# ── Built-in tool names ───────────────────────────────────────────────────────

BUILTIN_TOOL_NAMES = ["read", "bash", "edit", "write", "grep", "find"]

# ── Tools excluded from sub-agents (no recursive sub-agents) ──────────────────

EXCLUDED_TOOL_NAMES = ["agent", "Agent", "stop_agent", "StopAgent", "agent_status", "AgentStatus"]


# ═══════════════════════════════════════════════════════════════════════════════
# AgentTypeRegistry
# ═══════════════════════════════════════════════════════════════════════════════

class AgentTypeRegistry:
    """Unified runtime registry of all agents (defaults + user-defined)."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentConfig] = {}
        self._user_agent_dir: str = ""
        self._project_agent_dir: str = ""

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        agents: dict[str, AgentConfig],
        disable_defaults: bool = False,
    ) -> None:
        """Register agents into the registry, replacing existing entries."""
        self._agents.clear()
        if not disable_defaults:
            for name, config in DEFAULT_AGENTS.items():
                self._agents[name] = config
        for name, config in agents.items():
            self._agents[name] = config

    def set_scan_dirs(self, user_dir: str, project_dir: str) -> None:
        """Set directories for on-demand agent discovery."""
        self._user_agent_dir = user_dir
        self._project_agent_dir = project_dir

    async def discover_new(
        self,
        worktree_dir: str | None = None,
        disable_defaults: bool = False,
    ) -> int:
        """Scan known directories and register newly discovered agents."""
        user_agents = scan_agent_files_in_dir(self._user_agent_dir, "user") if self._user_agent_dir else []
        project_agents = scan_agent_files_in_dir(self._project_agent_dir, "project") if self._project_agent_dir else []

        defaults: dict[str, AgentConfig] = {} if disable_defaults else DEFAULT_AGENTS
        merged = merge_agents(defaults, user_agents, project_agents)

        count = 0
        for name, config in merged.items():
            if name not in self._agents:
                self._agents[name] = config
                count += 1

        # Also scan worktree-local agents
        if worktree_dir:
            wt_agents = scan_agent_files_in_dir(worktree_dir, "project")
            wt_merged = merge_agents({}, [], wt_agents)
            for name, config in wt_merged.items():
                if name not in self._agents:
                    self._agents[name] = config
                    count += 1

        return count

    # ── Lookup ────────────────────────────────────────────────────────────

    def resolve(self, name: str) -> str | None:
        """Case-insensitive type name lookup. Also matches display_name."""
        if not name:
            return None
        if name in self._agents:
            return name
        lower = name.lower()
        for key, config in self._agents.items():
            if key.lower() == lower:
                return key
            if (config.display_name or "").lower() == lower:
                return key
        return None

    def get_config(self, name: str) -> AgentConfig | None:
        """Get agent config by name (case-insensitive)."""
        key = self.resolve(name)
        return self._agents.get(key) if key else None

    def get_available_types(self) -> list[str]:
        """Get all visible (non-hidden) agent type names."""
        return [
            name for name, config in self._agents.items()
            if not config.hidden
        ]

    def get_all_types(self) -> list[str]:
        """Get all agent type names including hidden."""
        return list(self._agents.keys())

    # ── Tool resolution ───────────────────────────────────────────────────

    def get_tool_names_for_type(self, type_name: str) -> list[str]:
        """Get tool names to register for a given agent type."""
        config = self.get_config(type_name)
        if config and config.registered_tools:
            return config.registered_tools
        return list(BUILTIN_TOOL_NAMES)

    def resolve_visible_tools(
        self,
        active_tools: list[str],
        tools: bool | list[str] | None = None,
        exclude_tools: list[str] | None = None,
        ext_tool_map: dict[str, list[str]] | None = None,
    ) -> list[str] | None:
        """
        Resolve the visible tool set for an agent type from its config.

        Returns None when no filtering is needed, otherwise the filtered list.
        """
        # Blacklist mode: exclude_tools set and tools not set as whitelist
        if exclude_tools and not isinstance(tools, list):
            exclude_set = set(exclude_tools)
            filtered = [
                t for t in active_tools
                if t not in EXCLUDED_TOOL_NAMES and t not in exclude_set
            ]
            return filtered if len(filtered) != len(active_tools) else None

        if isinstance(tools, list):
            # Whitelist mode
            allowed = set(tools)
            visible = [
                t for t in active_tools
                if t not in EXCLUDED_TOOL_NAMES and t in allowed
            ]
            return visible

        if tools is False:
            return []

        # tools is True or None — all tools visible (except excluded)
        has_excluded = any(t in EXCLUDED_TOOL_NAMES for t in active_tools)
        if not has_excluded:
            return None  # No filtering needed
        return [t for t in active_tools if t not in EXCLUDED_TOOL_NAMES]
