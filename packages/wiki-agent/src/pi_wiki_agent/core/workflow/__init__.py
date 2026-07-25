"""
Workflow engine — parallel agent orchestration for wiki-agent.

Core primitives:
    run_workflow(script, options)  — execute a pre-written workflow script
    parse_workflow_script(script)  — validate and split script into meta + body
    WorkflowAgent                  — spawns in-memory subagent sessions

Usage (pre-written script, not model-generated)::

    script = Path(".wiki/workflows/sync_commit.py").read_text()
    agent = WorkflowAgent(cwd=project_path, model=model, ...)
    result = await run_workflow(script, WorkflowRunOptions(
        args={"changed_files": [...]},
        agent=agent,
        concurrency=8,
    ))
"""
from .workflow import (
    AgentOptions,
    WorkflowMeta,
    WorkflowMetaPhase,
    WorkflowRunOptions,
    WorkflowRunResult,
    parse_workflow_script,
    run_workflow,
)
from .workflow_agent import WorkflowAgent
from .structured_output import StructuredOutputCapture, create_structured_output_tool

__all__ = [
    "AgentOptions",
    "WorkflowMeta",
    "WorkflowMetaPhase",
    "WorkflowRunOptions",
    "WorkflowRunResult",
    "parse_workflow_script",
    "run_workflow",
    "WorkflowAgent",
    "StructuredOutputCapture",
    "create_structured_output_tool",
]
