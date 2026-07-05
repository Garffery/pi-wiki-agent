"""
Tool wrappers for extensions.

Wraps agent tools with extension event callbacks, allowing extensions to
intercept tool calls and results.

Mirrors core/extensions/wrapper.ts
"""

from __future__ import annotations

from typing import Any, Callable


def wrap_registered_tool(registered_tool: Any, runner: Any) -> dict[str, Any]:
    """Wrap a RegisteredTool definition into an AgentTool-compatible dict."""
    definition = registered_tool if not hasattr(registered_tool, "definition") else registered_tool.definition

    async def _execute(tool_call_id: str, params: dict, cancel_event: Any = None, on_update: Any = None) -> Any:
        ctx = runner.create_context()
        return await definition.execute(tool_call_id, params, cancel_event, on_update, ctx)

    return {
        "name": definition.name,
        "label": definition.label,
        "description": definition.description,
        "parameters": definition.parameters,
        "execute": _execute,
    }


def wrap_registered_tools(registered_tools: list[Any], runner: Any) -> list[dict[str, Any]]:
    """Wrap all registered tools into AgentTool dicts."""
    return [wrap_registered_tool(rt, runner) for rt in registered_tools]


def _tool_attr(tool, name: str, default=None):
    """Duck-type accessor: works with both dict and object tools."""
    if isinstance(tool, dict):
        return tool.get(name, default)
    return getattr(tool, name, default)


def _copy_tool(tool, **overrides):
    """Duck-type copy: dict returns dict, Pydantic model returns new model."""
    if isinstance(tool, dict):
        out = dict(tool)
        out.update(overrides)
        return out
    return tool.model_copy(update=overrides)


def wrap_tool_with_extensions(tool: dict[str, Any] | Any, runner: Any) -> dict[str, Any] | Any:
    """Wrap an agent tool with extension interception callbacks.

    Supports both dict and AgentTool (Pydantic model) tools.

    - Emits tool_call before execution (can block)
    - Emits tool_result after execution (can modify result)
    """
    from pi_coding_agent.core.extensions.types import ToolCallEvent, ToolResultEvent

    original_execute = _tool_attr(tool, "execute")
    tool_name = _tool_attr(tool, "name")

    async def _wrapped_execute(
        tool_call_id: str,
        params: dict,
        cancel_event: Any = None,
        on_update: Any = None,
    ) -> Any:
        if runner.has_handlers("tool_call"):
            call_event = ToolCallEvent(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                input=params,
            )
            call_result = await runner.emit_tool_call(call_event)
            if call_result and _tool_attr(call_result, "block", False):
                reason = _tool_attr(call_result, "reason", None) or "Tool execution was blocked by an extension"
                raise RuntimeError(reason)

        try:
            result = await original_execute(tool_call_id, params, cancel_event, on_update)

            if runner.has_handlers("tool_result"):
                content = result.get("content", []) if isinstance(result, dict) else getattr(result, "content", [])
                details = result.get("details") if isinstance(result, dict) else getattr(result, "details", None)
                result_event = ToolResultEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    input=params,
                    content=content,
                    is_error=False,
                    details=details,
                )
                result_result = await runner.emit_tool_result(result_event)
                if result_result:
                    new_content = _tool_attr(result_result, "content", None)
                    new_details = _tool_attr(result_result, "details", None)
                    if isinstance(result, dict):
                        out = dict(result)
                        if new_content is not None:
                            out["content"] = new_content
                        if new_details is not None:
                            out["details"] = new_details
                        return out
                    else:
                        if new_content is not None:
                            result.content = new_content
                        if new_details is not None:
                            result.details = new_details

            return result

        except Exception as err:
            if runner.has_handlers("tool_result"):
                err_event = ToolResultEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    input=params,
                    content=[{"type": "text", "text": str(err)}],
                    is_error=True,
                )
                await runner.emit_tool_result(err_event)
            raise

    return _copy_tool(tool, execute=_wrapped_execute)


def wrap_tools_with_extensions(tools: list[Any], runner: Any) -> list[Any]:
    """Wrap all agent tools with extension interception."""
    return [wrap_tool_with_extensions(tool, runner) for tool in tools]
