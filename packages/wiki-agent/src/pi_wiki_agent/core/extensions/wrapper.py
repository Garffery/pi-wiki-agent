"""Tool wrappers for extensions — intercepts tool_call/tool_result events."""

from __future__ import annotations

from typing import Any


def _tool_attr(tool, name: str, default=None):
    if isinstance(tool, dict):
        return tool.get(name, default)
    return getattr(tool, name, default)


def _copy_tool(tool, **overrides):
    if isinstance(tool, dict):
        out = dict(tool)
        out.update(overrides)
        return out
    return tool.model_copy(update=overrides)


def wrap_tool_with_extensions(tool: dict[str, Any] | Any, runner: Any) -> dict[str, Any] | Any:
    """Wrap an agent tool with extension event dispatch.

    Extension events (tool_call/tool_result) are forwarded to registered extension
    handlers. This wrapper does NOT include built-in wiki guards — those are handled
    by wiki_tool_wrapper.py.
    """
    from .types import ToolCallEvent, ToolResultEvent

    original_execute = _tool_attr(tool, "execute")
    tool_name = _tool_attr(tool, "name")

    async def _wrapped_execute(tool_call_id: str, params: dict, cancel_event=None, on_update=None):
        # ── Extension tool_call event ────────────────────────────────────
        call_event = ToolCallEvent(tool_call_id=tool_call_id, tool_name=tool_name, input=params or {})
        call_result = await runner.emit_tool_call(call_event)
        if call_result and getattr(call_result, "block", False):
            raise RuntimeError(getattr(call_result, "reason", "Blocked by extension"))

        # ── Execute original tool ────────────────────────────────────────
        try:
            result = await original_execute(tool_call_id, params, cancel_event, on_update)

            content = result.get("content", []) if isinstance(result, dict) else getattr(result, "content", [])
            details = result.get("details") if isinstance(result, dict) else getattr(result, "details", None)
            result_event = ToolResultEvent(
                tool_call_id=tool_call_id, tool_name=tool_name,
                input=params or {}, content=content, details=details, is_error=False,
            )
            rr = await runner.emit_tool_result(result_event)
            if rr:
                nc = getattr(rr, "content", None)
                nd = getattr(rr, "details", None)
                if isinstance(result, dict):
                    out = dict(result)
                    if nc is not None: out["content"] = nc
                    if nd is not None: out["details"] = nd
                    return out
                else:
                    if nc is not None: result.content = nc
                    if nd is not None: result.details = nd
            return result
        except Exception as err:
            err_event = ToolResultEvent(
                tool_call_id=tool_call_id, tool_name=tool_name,
                input=params or {}, content=[{"type": "text", "text": str(err)}], is_error=True,
            )
            await runner.emit_tool_result(err_event)
            raise

    return _copy_tool(tool, execute=_wrapped_execute)


def wrap_tools_with_extensions(tools: list[Any], runner: Any) -> list[Any]:
    return [wrap_tool_with_extensions(tool, runner) for tool in tools]
