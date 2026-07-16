"""Lightweight wiki page structure guard — string-level checks on edit/write params.

Zero disk I/O. Runs per-tool-call before the actual write. Checks that the LLM's
edit/write parameters don't remove critical structural elements from wiki pages.
"""

from __future__ import annotations

import re

_WIKI_SECTION_OPEN = re.compile(r"<!--\s*WIKI_SECTION:")
_WIKI_SECTION_CLOSE = re.compile(r"<!--\s*WIKI_SECTION_END")
_SOURCE_LINK = re.compile(r"\*\*source\*\*:\[")


class LightGuard:
    """Zero-I/O structural guard for wiki page edits.

    Validates edit/write tool parameters before execution, blocking operations
    that would remove WIKI_SECTION markers or source links. No file reads —
    purely regex matching on the params already in memory.
    """

    def check_params(self, tool_name: str, params: dict) -> str | None:
        """Check tool params for structural violations. Returns error message or None.

        Args:
            tool_name: Tool name ("edit" or "write").
            params: Tool call parameters.

        Returns:
            Error string if the operation would violate structure, None if safe.
        """
        if tool_name == "edit":
            return self._check_edit(
                params.get("old_string", ""),
                params.get("new_string", ""),
            )
        elif tool_name == "write":
            return self._check_write(params.get("content", ""))
        return None

    # ── edit ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_edit(old_string: str, new_string: str) -> str | None:
        """Check that structural markers present in old_string are preserved in new_string."""
        if not old_string or not new_string:
            return None

        # WIKI_SECTION open marker
        if _WIKI_SECTION_OPEN.search(old_string):
            if not _WIKI_SECTION_OPEN.search(new_string):
                return (
                    "不允许删除 WIKI_SECTION 开标记。你的 old_string 中包含了 "
                    "`<!-- WIKI_SECTION:...>` 但 new_string 中没有。"
                    "请保留 section 标记，只修改标记内的文本内容。"
                )

        # WIKI_SECTION close marker
        if _WIKI_SECTION_CLOSE.search(old_string):
            if not _WIKI_SECTION_CLOSE.search(new_string):
                return (
                    "不允许删除 WIKI_SECTION_END 闭标记。你的 old_string 中包含了 "
                    "`<!-- WIKI_SECTION_END -->` 但 new_string 中没有。"
                    "请保留 section 标记，只修改标记内的文本内容。"
                )

        # source link
        if _SOURCE_LINK.search(old_string):
            if not _SOURCE_LINK.search(new_string):
                return (
                    "不允许删除 **source** 溯源行。你的 old_string 中包含了 "
                    "`**source**:[...](file://...)` 但 new_string 中没有。"
                    "溯源行标记了内容对应的源文件，请保留它们。"
                )

        return None

    # ── write ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_write(content: str) -> str | None:
        """Check full write content for wiki structure issues.

        Only validates if the content looks like a wiki page (has WIKI_SECTION markers).
        Non-wiki files pass through without checks.
        """
        if not content:
            return None

        opens = len(_WIKI_SECTION_OPEN.findall(content))
        closes = len(_WIKI_SECTION_CLOSE.findall(content))

        if opens == 0 and closes == 0:
            return None  # not a wiki page

        if opens != closes:
            return (
                f"WIKI_SECTION 标记不配对：发现 {opens} 个开标记、{closes} 个闭标记。"
                "每个 `<!-- WIKI_SECTION:xxx -->` 必须有对应的 `<!-- WIKI_SECTION_END -->`。"
                "请检查是否遗漏了某个闭标记。"
            )

        return None
