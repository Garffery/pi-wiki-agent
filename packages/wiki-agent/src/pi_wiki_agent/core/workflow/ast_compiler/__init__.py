"""
AST-based workflow compiler — YAML → Python script via ``ast`` module.

Replaces the string-concatenation compiler in ``compiler.py``.
The output script string is fed to ``run_workflow()`` unchanged.

Usage::

    from pi_wiki_agent.core.workflow.ast_compiler import compile_workflow_yaml

    script = compile_workflow_yaml(yaml_text)
    result = await run_workflow(script, options)
"""
from __future__ import annotations

import ast

from .ir import (
    PhaseDef,
    StepDef,
    VariableDef,
    WorkflowDef,
    parse_workflow_yaml,
)
from .schema import compile_schema
from .builder import WorkflowASTBuilder


def compile_workflow_yaml(yaml_text: str, agent_defs: dict | None = None) -> str:
    """Compile a YAML workflow definition into a Python script string.

    Args:
        yaml_text: Raw YAML content defining the workflow.
        agent_defs: Unused — kept for API compatibility with the old compiler.

    Returns:
        A Python script string ready for ``run_workflow()``.
    """
    print("[ast_compiler] Using AST-based compiler (new version)")
    wf = parse_workflow_yaml(yaml_text)
    builder = WorkflowASTBuilder(wf)
    mod = builder.build()
    return ast.unparse(mod)


__all__ = [
    "PhaseDef",
    "StepDef",
    "VariableDef",
    "WorkflowDef",
    "compile_schema",
    "compile_workflow_yaml",
    "parse_workflow_yaml",
]
