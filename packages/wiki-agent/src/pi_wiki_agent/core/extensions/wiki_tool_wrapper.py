"""Built-in wiki tool wrapper — applies wiki guards to all tools unconditionally.

Separate from the extension wrapper (wrapper.py) by design:
- wiki_tool_wrapper: built-in wiki guards (edit page restrictions), always active
- wrapper: extension event dispatch (tool_call/tool_result), only when extensions are loaded

Usage::

    guard = WikiToolGuard(cwd="/path/to/project")
    guard.set_allowed_pages({"section1.md", "section2.md"})
    tools = wrap_tools_with_wiki_guards(tools, guard)
    # guard.check_edit_allowed runs before every tool call
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...logging import logger


class WikiToolGuard:
    """Built-in guard that restricts edit/write operations to approved wiki pages.

    This is NOT an extension — it runs unconditionally for every tool call.
    Edit/write operations outside the approved set are blocked with a RuntimeError.
    """

    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd
        self._allowed_wiki_pages: set[str] = set()

    def set_allowed_pages(self, pages: set[str]) -> None:
        """Set the list of wiki pages that the agent is allowed to edit in the current request."""
        self._allowed_wiki_pages = pages
        if pages:
            logger.info("设置允许修改页面: {}", sorted(pages))
        else:
            logger.info("清空允许修改页面限制")

    def check_edit_allowed(self, tool_name: str, params: dict) -> Any | None:
        """Check whether an edit/write operation targets an allowed wiki page.

        Returns None if allowed, or a block-result object (with ``block=True``)
        if the operation should be rejected.
        """
        logger.info("拦截工具===> tool_name={} params={}", tool_name, params)
        if tool_name not in ("edit", "write"):
            return None
        if not self._allowed_wiki_pages:
            return None

        file_path = params.get("path", "")
        if not file_path:
            return None

        p = Path(file_path)
        if not p.is_absolute():
            p = Path(self._cwd) / file_path

        wiki_root = Path(self._cwd) / ".wiki"
        try:
            rel = str(p.relative_to(wiki_root)).replace("\\", "/")
        except ValueError:
            logger.warning("拦截编辑: 文件不在 .wiki 下 tool={} path={}", tool_name, file_path)
            allowed_list = ", ".join(sorted(self._allowed_wiki_pages))
            return _block(
                f"禁止修改文件 \"{file_path}\"，它不在 .wiki 目录下。"
                f"本次请求只允许修改以下 wiki 页面: {allowed_list}"
            )

        if rel not in self._allowed_wiki_pages:
            logger.warning("拦截编辑: 不在允许列表中 tool={} file={} allowed={}", tool_name, rel, sorted(self._allowed_wiki_pages))
            allowed_list = ", ".join(sorted(self._allowed_wiki_pages))
            return _block(
                f"禁止修改 \"{rel}\"，本次请求只允许修改以下 wiki 页面: {allowed_list}。"
                f"请检查你的修改目标，只修改上述允许的页面。"
            )

        logger.debug("编辑放行: tool={} file={}", tool_name, rel)
        return None


def _block(reason: str) -> Any:
    """Create a block-result object."""
    return type("BlockResult", (), {"block": True, "reason": reason})()


# ── Wrapper functions ──────────────────────────────────────────────────────────


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


def wrap_tool_with_wiki_guard(tool: dict[str, Any] | Any, guard: WikiToolGuard) -> dict[str, Any] | Any:
    """Wrap a built-in tool with the wiki page edit guard.

    The guard's ``check_edit_allowed`` runs unconditionally before every tool call,
    blocking edit/write operations that target unapproved wiki pages.
    """
    original_execute = _tool_attr(tool, "execute")
    tool_name = _tool_attr(tool, "name")

    async def _guarded_execute(tool_call_id: str, params: dict, cancel_event=None, on_update=None):
        block_result = guard.check_edit_allowed(tool_name, params or {})
        if block_result and getattr(block_result, "block", False):
            raise RuntimeError(getattr(block_result, "reason", "Blocked by wiki guard"))
        return await original_execute(tool_call_id, params, cancel_event, on_update)

    return _copy_tool(tool, execute=_guarded_execute)


def wrap_tools_with_wiki_guards(tools: list[Any], guard: WikiToolGuard) -> list[Any]:
    return [wrap_tool_with_wiki_guard(tool, guard) for tool in tools]
