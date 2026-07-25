"""
Workflow tool definition — registers the `workflow` tool in Pi.

Mirrors src/workflow-tool.ts from pi-dynamic-workflows.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from pi_coding_agent.core.auth_storage import AuthStorage
from pi_coding_agent.core.model_registry import ModelRegistry

from .workflow import (
    WorkflowRunOptions,
    parse_workflow_script,
    run_workflow,
)

WORKFLOW_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {
            "type": "string",
            "description": (
                "Required raw Python workflow script, with no Markdown fences. "
                "First statement: meta = { 'name': 'short_snake_case', 'description': 'non-empty description' }. "
                "meta['phases'] is optional documentation; live progress is driven by phase(title). "
                "Use phase('Name'), agent(prompt, opts), parallel(list_of_functions), pipeline(items, *stages), "
                "log(message), args, and budget. The workflow must call agent() at least once. "
                "parallel() requires functions, not coroutines: await parallel([lambda: agent(...)])."
            ),
        },
        "args": {
            "description": "Optional JSON value exposed to the workflow script as global `args`.",
        },
    },
    "required": ["script"],
}


def create_workflow_tool():
    """Create the workflow tool definition dict."""

    async def execute_workflow(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
        script = params["script"]
        script = _normalize_script(script)

        # Parse early to validate
        meta, _body = parse_workflow_script(script)

        cwd = _extract_cwd(ctx)
        model = _extract_model(ctx)

        try:
            result = await run_workflow(
                script,
                WorkflowRunOptions(
                    args=params.get("args"),
                    cwd=cwd,
                    concurrency=4,
                    model=model,
                    model_registry=ModelRegistry(),
                    auth_storage=AuthStorage(),
                ),
            )
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Workflow failed: {e}"}],
                "details": {"error": str(e), "meta": {"name": meta.name}},
            }

        if result.agent_count == 0:
            return {
                "content": [{
                    "type": "text",
                    "text": "workflow scripts must call agent() at least once; this workflow declared phases but did not run any subagents",
                }],
                "details": {"error": "no agents called", "meta": {"name": meta.name}},
            }

        return {
            "content": [{
                "type": "text",
                "text": (
                    f"Workflow {result.meta.name} completed with {result.agent_count} agent(s) "
                    f"in {result.duration_ms:.0f}ms.\n"
                    f"Phases: {', '.join(result.phases) if result.phases else 'none'}\n"
                    f"Logs: {len(result.logs)} lines\n\n"
                    f"Result:\n{json.dumps(result.result, indent=2, ensure_ascii=False)}"
                ),
            }],
            "details": {
                "meta": {
                    "name": result.meta.name,
                    "description": result.meta.description,
                },
                "phases": result.phases,
                "logs": result.logs,
                "agent_count": result.agent_count,
                "duration_ms": result.duration_ms,
                "result": result.result,
            },
        }

    return {
        "name": "workflow",
        "label": "Workflow",
        "description": (
            "Execute a deterministic Python workflow that orchestrates multiple subagents "
            "with agent(), parallel(), and pipeline(). "
            "script is required raw Python. It must start with meta = { 'name', 'description' } "
            "and must call agent() at least once; phases are optional metadata."
        ),
        "parameters": WORKFLOW_TOOL_SCHEMA,
        "execute": execute_workflow,
        "prompt_snippet": (
            "Run a deterministic Python workflow. Required script header: "
            "meta = { 'name': 'short_snake_case', 'description': 'non-empty description' }. "
            "Use phase(title) at runtime to create progress groups."
        ),
        "prompt_guidelines": _PROMPT_GUIDELINES,
    }


_PROMPT_GUIDELINES = [
    "Use workflow only when the user explicitly asks for a workflow, workflows, fan-out, or multi-agent orchestration.",
    "For workflow, always pass one raw Python string in the required script parameter; do not include Markdown fences or prose around the script.",
    "For workflow, the script's first statement must be `meta = { 'name': 'short_snake_case', 'description': 'non-empty human description' }`; meta['name'] and meta['description'] are required non-empty strings, and meta['phases'] is optional metadata for a stable upfront outline.",
    "For workflow, write plain Python after the meta assignment. Do not use import statements, open(), eval(), exec(), compile(), or __import__().",
    "For workflow, available globals are agent(prompt, opts), parallel(thunks), pipeline(items, *stages), phase(title), log(message), args, cwd, and budget. Every workflow must call agent() at least once; do not use workflow only to declare phases or return a static object.",
    "For workflow, call phase(title) when a new group of work starts. Phase names may be conditional or built in a loop; do not predeclare speculative phases just in case.",
    "For workflow, prefer it for decomposable work: repository inspection, independent research/checks, multi-perspective review, or fan-out/fan-in synthesis. Do not use it for a single quick file read/edit or when ordinary tools are enough.",
    "For workflow, parallel() takes functions, not coroutines: use `await parallel([lambda: agent('...', {'label': '...'})])`, never `await parallel([agent(...)])`. Results are returned in input order.",
    "For workflow, pipeline(items, *stages) runs each item through stages sequentially, while different items may run concurrently. Each stage receives (previous_value, original_item, index).",
    "For workflow, every agent() call should include a unique short label in opts, 2-5 words, such as {'label': 'repo inventory'} or {'label': 'source modules'}; unique labels make live status and error reporting readable.",
    "For workflow, failed agent(), parallel(), or pipeline() branches return None and log the failure unless the workflow is aborted. Check for None before synthesizing conclusions.",
    "For workflow, include a final synthesis/assertion agent when combining multiple subagent results; return a compact JSON-serializable value with ok/verdict plus the important outputs.",
    "For workflow, if agent() needs machine-readable output, pass a plain JSON Schema via opts['schema']; agent() will return the validated dict. Use JSON Schema syntax.",
    "For workflow, do not assume the parent assistant has repository code context inside subagents; include enough task context and relevant paths in each agent prompt.",
    "For workflow, agent opts dict supports: label (str), phase (str), schema (dict, JSON Schema), model (str), isolation (str), agent_type (str).",
    "For workflow, use dict opts for agent() arguments: agent('prompt', {'label': 'my agent'}), not agent('prompt', 'my label').",
]


def _normalize_script(script: str) -> str:
    """Strip optional markdown fences from the script."""
    text = script.strip()
    fence = re.match(r"^```(?:py|python)?\s*\n([\s\S]*?)\n```\s*$", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    return text


def _extract_cwd(ctx: Any) -> str:
    """Extract cwd from context, falling back to process.cwd()."""
    if ctx is not None:
        cwd_attr = getattr(ctx, "cwd", None)
        if cwd_attr:
            return str(cwd_attr)
    return os.getcwd()


def _extract_model(ctx: Any) -> Any:
    """Extract model from context if available."""
    if ctx is not None:
        model = getattr(ctx, "model", None)
        if model is not None:
            return model
    return None
