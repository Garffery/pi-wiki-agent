"""Chain types — mirrors pi-subagents chain configuration model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChainStep:
    """A single step in a chain execution.

    Mirrors SequentialStep in pi-subagents.
    """
    # Agent name to execute this step
    agent: str
    # Task template. Defaults: first step = "{task}", subsequent = "{previous}"
    task: str | None = None
    # Named output key — result can be referenced by later steps via {outputs.name}
    as_: str | None = None
    # Output file path for this step's result
    output: str | None = None
    # Default files to read before starting
    reads: list[str] | None = None
    # Model override (format: "provider:model_id")
    model: str | None = None
    # Thinking level override
    thinking: str | None = None
    # Extra settings passed through to WikiSession
    extra: dict[str, Any] | None = None


@dataclass
class ChainConfig:
    """Configuration for a chain execution.

    Mirrors the params passed to executeChain in pi-subagents.
    """
    # Chain steps (sequential)
    steps: list[ChainStep]
    # Original user task — replaces {task} in templates
    task: str
    # Project root path
    project_path: str
    # Chain working directory (default: auto-created temp dir)
    chain_dir: str | None = None
    # Maximum subagent depth (unused in wiki-agent, kept for API compat)
    max_subagent_depth: int = 3
    # Custom template variables — accessible via {vars.key} in step templates
    vars: dict[str, str] | None = None


@dataclass
class StepResult:
    """Result from a single chain step."""
    agent: str
    step_index: int
    output: str | None = None
    exit_code: int = 0
    error: str | None = None
    pages_modified: list[str] = field(default_factory=list)
    output_file: str | None = None


@dataclass
class ChainResult:
    """Result from a complete chain execution."""
    steps: list[StepResult] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    # Aggregated across all steps
    all_pages_modified: list[str] = field(default_factory=list)
    # Named outputs from steps with as_ set
    outputs: dict[str, str] = field(default_factory=dict)

    @property
    def last_output(self) -> str | None:
        """Get output from the last successful step."""
        for step in reversed(self.steps):
            if step.output is not None:
                return step.output
        return None
