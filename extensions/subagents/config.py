"""
config.py — Config persistence for the subagents extension.

Reads/writes ~/.pi/agent/subagents.json with atomic saves.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .models import SessionModelOverrides, SubagentsConfig


def _config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".pi", "agent")


def _config_path() -> str:
    return os.path.join(_config_dir(), "subagents.json")


def _custom_prompt_path() -> str:
    return os.path.join(_config_dir(), "subagents-prompt.md")


def load_config() -> SubagentsConfig:
    """Read config from disk, merged with defaults."""
    raw: dict[str, Any] = {}
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    agent_raw = raw.get("agent", {})
    concurrency_raw = raw.get("concurrency", {})

    # Separate known keys from per-agent overrides
    known_agent_keys = {
        "default", "forceBackground", "graceTurns", "systemPromptMode",
        "includeContextFiles", "defaultThinking", "defaultMaxTurns",
        "loadSkillsImplicitly", "loadExtensionsImplicitly",
        "disableDefaultAgents", "showCost", "outputThinkingBufferSize",
    }
    overrides = {k: v for k, v in agent_raw.items() if k not in known_agent_keys and isinstance(v, str)}

    agent = SubagentsConfig.AgentSection(
        default=agent_raw.get("default"),
        force_background=agent_raw.get("forceBackground", False),
        grace_turns=agent_raw.get("graceTurns", 6),
        system_prompt_mode=agent_raw.get("systemPromptMode", "replace"),
        include_context_files=agent_raw.get("includeContextFiles", True),
        default_thinking=agent_raw.get("defaultThinking"),
        default_max_turns=agent_raw.get("defaultMaxTurns"),
        load_skills_implicitly=agent_raw.get("loadSkillsImplicitly", True),
        load_extensions_implicitly=agent_raw.get("loadExtensionsImplicitly", True),
        disable_default_agents=agent_raw.get("disableDefaultAgents", False),
        show_cost=agent_raw.get("showCost", False),
        output_thinking_buffer_size=agent_raw.get("outputThinkingBufferSize", 0),
        overrides=overrides,
    )

    concurrency = SubagentsConfig.ConcurrencySection(
        default=concurrency_raw.get("default", 4),
        providers=concurrency_raw.get("providers", {}),
        models=concurrency_raw.get("models", {}),
    )

    return SubagentsConfig(agent=agent, concurrency=concurrency)


def save_config(config: SubagentsConfig) -> None:
    """Write config to disk with atomic rename."""
    # Serialize agent section, extracting overrides into flat dict
    a = config.agent
    agent_dict: dict[str, Any] = {
        "default": a.default,
        "forceBackground": a.force_background,
        "graceTurns": a.grace_turns,
        "systemPromptMode": a.system_prompt_mode,
        "includeContextFiles": a.include_context_files,
        "disableDefaultAgents": a.disable_default_agents,
        "showCost": a.show_cost,
        "outputThinkingBufferSize": a.output_thinking_buffer_size,
    }
    if a.default_thinking is not None:
        agent_dict["defaultThinking"] = a.default_thinking
    if a.default_max_turns is not None:
        agent_dict["defaultMaxTurns"] = a.default_max_turns
    agent_dict["loadSkillsImplicitly"] = a.load_skills_implicitly
    agent_dict["loadExtensionsImplicitly"] = a.load_extensions_implicitly
    # Merge per-agent overrides
    agent_dict.update(a.overrides)

    c = config.concurrency
    concurrency_dict: dict[str, Any] = {"default": c.default}
    if c.providers:
        concurrency_dict["providers"] = c.providers
    if c.models:
        concurrency_dict["models"] = c.models

    full = {"agent": agent_dict, "concurrency": concurrency_dict}

    dir_path = _config_dir()
    config_path = _config_path()
    tmp_path = config_path + ".tmp"

    try:
        os.makedirs(dir_path, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(full, f, indent=2)
        os.replace(tmp_path, config_path)
    except OSError:
        pass


class ConfigStore:
    """
    Central config store owning persisted config + session overrides.

    Mirrors the TS ConfigStore — authoritative for all config access.
    """

    def __init__(self) -> None:
        self.config: SubagentsConfig = load_config()
        self.session_overrides = SessionModelOverrides()
        self._deps: dict[str, Any] = {}

    def reload(self) -> None:
        """Reload config from disk."""
        self.config = load_config()

    def model_for(
        self,
        subagent_type: str,
        parent_model_id: str,
        agent_config: Any = None,
    ) -> str:
        """Resolve model for a subagent type using 6-level precedence."""
        from .models import resolve_model as _resolve_model
        return _resolve_model(
            subagent_type=subagent_type,
            agent_config=agent_config,
            config=self.config,
            parent_model_id=parent_model_id,
            session_overrides=self.session_overrides,
        )

    def set_session_override(self, agent_type: str, model: str | None) -> None:
        """Set a session-only model override."""
        if agent_type == "default":
            self.session_overrides.default = model
        else:
            self.session_overrides.overrides[agent_type] = model

    def clear_session_overrides(self) -> None:
        """Clear all session overrides."""
        self.session_overrides = SessionModelOverrides()

    def set_deps(self, deps: dict[str, Any]) -> None:
        """Register dependency references (manager, widget, etc.)."""
        self._deps.update(deps)

    def dispose(self) -> None:
        """Clear session state."""
        self.clear_session_overrides()
        self._deps.clear()
