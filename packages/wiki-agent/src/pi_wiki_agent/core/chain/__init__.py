"""Chain execution — serial multi-agent orchestration for wiki-agent.

Mirrors pi-subagents chain mechanism:
  for each step:
    resolve template → create session → prompt → collect result → handoff

Usage::

    # Generic chain
    from pi_wiki_agent.core.chain import ChainConfig, ChainStep, execute_chain

    config = ChainConfig(
        steps=[
            ChainStep(agent="diff-analyzer"),
            ChainStep(agent="wiki-planner"),
            ChainStep(agent="wiki-writer"),
        ],
        task="分析这次提交的变更并更新 wiki 文档",
        project_path="/path/to/project",
    )
    result = await execute_chain(config)

    # Commit-driven sync chain (with reverse index)
    from pi_wiki_agent.core.chain import execute_sync_chain

    result = await execute_sync_chain(
        project_path="/path/to/project",
        changed_files=["src/cli.py", "src/utils.py"],
        commit_message="feat: add export command",
        diff="...",
    )
"""

from .types import ChainConfig, ChainResult, ChainStep, StepResult
from .agent_loader import discover_agents, find_agent, AgentDefinition
from .templates import resolve_template, build_step_prompt
from .executor import execute_chain
from .wiki_chain import execute_sync_chain

__all__ = [
    "ChainConfig",
    "ChainResult",
    "ChainStep",
    "StepResult",
    "AgentDefinition",
    "discover_agents",
    "find_agent",
    "execute_chain",
    "execute_sync_chain",
    "resolve_template",
    "build_step_prompt",
]
