"""Wiki agent system prompt and commit prompt builders."""

from __future__ import annotations

from .indexer import WikiIndexer
from .metadata import IndexEntry

WIKI_SYSTEM_PROMPT = """\
你是一个 wiki 文档管理 agent。你的任务是根据代码变更来更新项目的 wiki 文档。

## 工作原则

1. **只修改标记内的内容** — 每个 wiki 页面的章节被 `<!-- WIKI_SECTION:名称>` 和 `<!-- WIKI_SECTION_END -->` 包裹，你只能在标记范围内修改内容
2. **保留标记和溯源** — 不要删除或修改 `<!-- WIKI_SECTION:...>` 标记和 `**source**:[文件](file://路径)` 行
3. **匹配文档风格** — 保持与页面其他章节一致的格式、语气和结构
4. **精确更新** — 根据代码 diff 中的实际变更来更新文档，不臆造不存在的功能
5. **保持链接** — 不修改 `[[wiki链接]]` 的格式和指向
6. **使用 edit 工具** — 优先用 edit 工具做精确替换，避免用 write 重写整个文件
"""


def build_commit_prompt(
    changed_files: list[str],
    commit_message: str,
    diff: str,
    affected: dict[str, list[IndexEntry]],
) -> str:
    """Build the user prompt for a VCS commit, telling the agent what to update.

    Args:
        changed_files: List of changed source file paths.
        commit_message: The commit message from VCS.
        diff: The unified diff of the commit.
        affected: Affected wiki sections grouped by wiki page, from get_affected_sections().

    Returns:
        A prompt string ready to pass to AgentSession.prompt().
    """
    parts: list[str] = []

    parts.append("## 代码提交\n")
    parts.append(f"提交信息: {commit_message}\n")
    parts.append(f"变更文件: {', '.join(changed_files)}\n")

    parts.append("## 代码变更 (diff)\n")
    parts.append("```diff")
    parts.append(diff)
    parts.append("```\n")

    parts.append("## 需要更新的 wiki 章节\n")

    if not affected:
        parts.append("没有找到与此提交相关的 wiki 章节。如果认为需要创建新页面或更新现有页面，请说明理由。\n")
        return "\n".join(parts)

    for wiki_page, entries in affected.items():
        sections = [e.section_id for e in entries]
        files = sorted({e.file for e in entries})
        parts.append(f"- **{wiki_page}** → 章节: {', '.join(sections)}（代码关联: {', '.join(files)}）")

    parts.append("")
    parts.append("请逐个读取上述 wiki 页面，分析 diff 中的代码变更，然后更新对应的章节内容。")
    parts.append("每个章节修改完毕后，简要说明做了什么改动。")

    return "\n".join(parts)
