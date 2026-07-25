"""
Terminating structured-output tool for workflow subagents.

Mirrors src/structured-output.ts from pi-dynamic-workflows.

When a subagent calls structured_output, the capture is populated with validated
params, and the WorkflowAgent.run() method detects this to return the structured result.
"""
from __future__ import annotations

from typing import Any

from pi_agent.types import AgentTool, AgentToolResult
from pi_ai.types import TextContent


class StructuredOutputCapture:
    """Mutable capture that records a structured_output tool call."""

    def __init__(self):
        self.value: Any = None
        self.called: bool = False


def create_structured_output_tool(
    schema: dict[str, Any],
    capture: StructuredOutputCapture,
    name: str = "structured_output",
) -> AgentTool:
    """
    Create a tool that captures its validated params as the subagent result.

    The agent loop calls execute() with pi-validated params. We capture them
    and return a confirmation. The WorkflowAgent detects capture.called and
    returns capture.value as the subagent result.
    """

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> AgentToolResult:
        capture.value = params
        capture.called = True
        return AgentToolResult(
            content=[TextContent(type="text", text="Structured output received.")],
            details=params,
        )

    return AgentTool(
        name=name,
        label="Structured Output",
        description="Return the final machine-readable result for this subagent task.",
        parameters=schema,
        execute=_execute,
    )
