"""
YAML workflow IR — pure data structures.

Parses a YAML workflow definition into typed dataclasses. No AST logic here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .schema import compile_schema

# ============================================================================
# IR data classes
# ============================================================================

PhaseMode = Literal["serial", "parallel", "dag", "pipeline"]


@dataclass
class VariableDef:
    """A named prompt variable from the ``variables:`` section."""
    name: str
    prompt: str  # raw text, may contain ${...} references


@dataclass
class StepDef:
    """A single step within a phase."""
    agent: str
    label: str | None = None          # may contain ${...}
    prompt: str | None = None         # may contain ${...}
    output_schema: dict | None = None  # compiled JSON Schema
    id: str | None = None             # dag mode: explicit task id
    depends_on: list[str] = field(default_factory=list)  # dag mode: dependency ids


@dataclass
class PhaseDef:
    """A workflow phase."""
    title: str
    mode: PhaseMode = "serial"
    for_each: str | None = None  # raw ${...} expression
    steps: list[StepDef] = field(default_factory=list)


@dataclass
class WorkflowDef:
    """Top-level workflow definition."""
    name: str
    description: str = ""
    concurrency: int = 8
    variables: list[VariableDef] = field(default_factory=list)
    phases: list[PhaseDef] = field(default_factory=list)


# ============================================================================
# YAML → IR parser
# ============================================================================


def parse_workflow_yaml(yaml_text: str) -> WorkflowDef:
    """Parse a YAML workflow definition into a :class:`WorkflowDef`.

    Raises :class:`ValueError` for invalid structure.
    """
    import yaml as _yaml

    doc = _yaml.safe_load(yaml_text)

    if not isinstance(doc, dict):
        raise ValueError("YAML top-level must be a dict, got " + type(doc).__name__)
    if not doc.get("name"):
        raise ValueError("workflow YAML must have a 'name' field")
    if not isinstance(doc.get("phases"), list) or len(doc["phases"]) == 0:
        raise ValueError("workflow YAML must have a non-empty 'phases' list")

    name = str(doc["name"]).strip()
    description = str(doc.get("description", "")).strip()
    concurrency = _parse_concurrency(doc.get("concurrency", 8))
    variables = _parse_variables(doc.get("variables"))
    phases = [_parse_phase(p, i) for i, p in enumerate(doc["phases"])]

    return WorkflowDef(
        name=name,
        description=description,
        concurrency=concurrency,
        variables=variables,
        phases=phases,
    )


def _parse_concurrency(raw: Any) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"concurrency must be an integer, got {raw!r}")
    return max(1, min(v, 16))


def _parse_variables(raw: Any) -> list[VariableDef]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise ValueError(f"variables must be a dict, got {type(raw).__name__}")
    result: list[VariableDef] = []
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError("variable names must be non-empty strings")
        result.append(VariableDef(name=k.strip(), prompt=str(v)))
    return result


def _parse_phase(raw: Any, index: int) -> PhaseDef:
    if not isinstance(raw, dict):
        raise ValueError(f"phase[{index}] must be a dict, got {type(raw).__name__}")

    title = raw.get("title", f"Phase{index}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"phase[{index}].title must be a non-empty string")

    mode_raw = raw.get("mode", "serial")
    if not isinstance(mode_raw, str) or mode_raw not in ("serial", "parallel", "dag", "pipeline"):
        raise ValueError(
            f"phase '{title}': mode must be one of serial/parallel/dag/pipeline, got {mode_raw!r}"
        )

    for_each = raw.get("for_each")
    if for_each is not None and not isinstance(for_each, str):
        raise ValueError(f"phase '{title}': for_each must be a string expression")

    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or len(steps_raw) == 0:
        raise ValueError(f"phase '{title}': must have a non-empty 'steps' list")

    steps = [_parse_step(s, i, title) for i, s in enumerate(steps_raw)]

    return PhaseDef(
        title=title.strip(),
        mode=mode_raw,
        for_each=for_each,
        steps=steps,
    )


def _parse_step(raw: Any, index: int, phase_title: str) -> StepDef:
    if not isinstance(raw, dict):
        raise ValueError(
            f"phase '{phase_title}' step[{index}]: must be a dict, got {type(raw).__name__}"
        )

    agent = raw.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError(
            f"phase '{phase_title}' step[{index}]: must have a non-empty 'agent' string"
        )

    label = raw.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(f"phase '{phase_title}' step[{index}]: 'label' must be a string")

    prompt = raw.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise ValueError(f"phase '{phase_title}' step[{index}]: 'prompt' must be a string")

    output_schema = compile_schema(raw.get("output_schema"))

    step_id = raw.get("id")
    if step_id is not None and not isinstance(step_id, str):
        raise ValueError(f"phase '{phase_title}' step[{index}]: 'id' must be a string")

    depends_on = raw.get("depends_on")
    if depends_on is not None:
        if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
            raise ValueError(
                f"phase '{phase_title}' step[{index}]: 'depends_on' must be a list of strings"
            )

    return StepDef(
        agent=agent.strip(),
        label=label.strip() if label else None,
        prompt=prompt,
        output_schema=output_schema,
        id=step_id.strip() if step_id else None,
        depends_on=list(depends_on) if depends_on else [],
    )
