"""
models.py — 6-level model precedence resolution.

Pure function — no side effects, no file I/O.

Precedence chain (highest to lowest):
  1. session_overrides[subagent_type]  (session per-type override)
  2. session_overrides["default"]      (session global default)
  3. config.agent[subagent_type]       (config per-type override)
  4. config.agent["default"]           (config global default)
  5. agent_config.model                (agent frontmatter)
  6. parent_model_id                   (inherit from parent)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionModelOverrides:
    """Session-only model overrides. Not persisted — cleared on session_start."""
    default: str | None = None
    overrides: dict[str, str | None] = field(default_factory=dict)

    def get(self, agent_type: str) -> str | None:
        return self.overrides.get(agent_type)


@dataclass
class SubagentsConfig:
    """Shape of the subagents.json config file."""

    @dataclass
    class AgentSection:
        default: str | None = None
        force_background: bool = False
        grace_turns: int = 6
        system_prompt_mode: str = "replace"  # "replace" | "inherit" | "custom"
        include_context_files: bool = True
        default_thinking: str | None = None
        default_max_turns: int | None = None
        load_skills_implicitly: bool = True
        load_extensions_implicitly: bool = True
        disable_default_agents: bool = False
        show_cost: bool = False
        output_thinking_buffer_size: int = 0
        # Per-agent-type overrides stored as extra fields
        overrides: dict[str, str | None] = field(default_factory=dict)

    @dataclass
    class ConcurrencySection:
        default: int = 4
        providers: dict[str, int] = field(default_factory=dict)
        models: dict[str, int] = field(default_factory=dict)

    agent: AgentSection = field(default_factory=AgentSection)
    concurrency: ConcurrencySection = field(default_factory=ConcurrencySection)


def resolve_model(
    subagent_type: str,
    agent_config: Any | None,  # AgentConfig or None
    config: SubagentsConfig,
    parent_model_id: str,
    session_overrides: SessionModelOverrides | None = None,
) -> str:
    """
    Resolve the model for a subagent invocation.

    Returns the first non-null, non-empty-string value from the
    6-level precedence chain. Falls back to parent_model_id.
    """
    candidates: list[str | None] = [
        session_overrides.get(subagent_type) if session_overrides else None,
        session_overrides.default if session_overrides else None,
        config.agent.overrides.get(subagent_type),
        config.agent.default,
        agent_config.model if agent_config else None,
        parent_model_id,
    ]

    for c in candidates:
        if isinstance(c, str) and len(c) > 0:
            return c

    return parent_model_id
