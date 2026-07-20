"""Wiki Generator — full wiki generation from a user-defined plan.

Reads .wiki/generation-plan.json, resolves source files, and uses LLM + WikiSession
to generate complete wiki pages with WIKI_SECTION markers and source links.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..logging import logger
from .chain.generation_plan import GenerationPlan, SectionSpec, PageSpec


@dataclass
class PageResult:
    page_path: str
    success: bool
    error: str | None = None


@dataclass
class GenerationResult:
    pages_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True


class WikiGenerator:
    """Generates wiki pages from a GenerationPlan."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._wiki_root = self._project_root / ".wiki"

    # ── Public API ──────────────────────────────────────────────────────────

    async def generate(
        self,
        plan: GenerationPlan | None = None,
        session_factory: Any = None,
        on_progress: Any = None,
    ) -> GenerationResult:
        """Generate all wiki pages defined in the plan.

        Args:
            plan: The generation plan. If None, loads from .wiki/generation-plan.json.
            session_factory: Optional factory to create WikiSession instances.
            on_progress: Optional callback(page_index, page_path, event_type, data).

        Returns:
            GenerationResult with pages created and errors.
        """
        if plan is None:
            plan = GenerationPlan.load(self._project_root)
        if plan is None:
            return GenerationResult(success=False, errors=["未找到 generation-plan.json"])

        os.makedirs(str(self._wiki_root), exist_ok=True)

        result = GenerationResult()

        for i, page_spec in enumerate(plan.pages):
            logger.info("生成页面 {}/{}: {}", i + 1, len(plan.pages), page_spec.path)
            if on_progress:
                on_progress(i, page_spec.path, "page_start", {"total": len(plan.pages)})

            try:
                page_result = await self._generate_page(page_spec, plan.style_guide, session_factory)
                if page_result.success:
                    result.pages_created.append(page_result.page_path)
                    if on_progress:
                        on_progress(i, page_spec.path, "page_done", {})
                else:
                    result.errors.append(f"{page_spec.path}: {page_result.error}")
                    if on_progress:
                        on_progress(i, page_spec.path, "page_error", {"error": page_result.error})
            except Exception as e:
                msg = f"{page_spec.path}: {e}"
                result.errors.append(msg)
                logger.error(msg)
                if on_progress:
                    on_progress(i, page_spec.path, "page_error", {"error": str(e)})

        # ── Rebuild reverse index ──────────────────────────────────────────
        if result.pages_created:
            try:
                from ..indexer import WikiIndexer
                indexer = WikiIndexer(self._project_root)
                for page_path in result.pages_created:
                    try:
                        indexer.update_page(page_path)
                    except Exception as e:
                        logger.warning("重建索引失败 ({}): {}", page_path, e)
                logger.info("已为 {} 个页面重建反向索引", len(result.pages_created))
            except Exception as e:
                logger.warning("重建反向索引失败: {}", e)

        result.success = len(result.errors) == 0
        logger.info(
            "生成完成: {} 页面成功, {} 错误",
            len(result.pages_created), len(result.errors),
        )
        return result

    # ── Per-page generation ─────────────────────────────────────────────────

    async def _generate_page(
        self,
        spec: PageSpec,
        style_guide: str,
        session_factory: Any = None,
    ) -> PageResult:
        output_path = self._wiki_root / spec.path
        os.makedirs(str(output_path.parent), exist_ok=True)

        # Build prompt
        prompt = self._build_page_prompt(spec, style_guide)

        # Create session and generate
        if session_factory:
            session = session_factory(
                project_path=str(self._project_root),
                system_prompt=None,   # Use wiki-generator agent prompt
                model=None,
                thinking="medium",
                active_tools=["write", "read", "grep", "find", "ls"],
            )
        else:
            from .agent_session import WikiSession
            session = WikiSession(
                project_root=str(self._project_root),
            )

        try:
            await session.prompt(prompt)
            text = session.get_last_assistant_text()
        finally:
            if hasattr(session, "close") and callable(session.close):
                try:
                    await session.close()
                except Exception:
                    pass

        # Validate the generated page exists
        if not output_path.exists():
            return PageResult(page_path=spec.path, success=False,
                            error="Agent 未写入文件，请检查模型是否支持 write 工具")

        content = output_path.read_text(encoding="utf-8")

        # Light validation
        opens = content.count("WIKI_SECTION:")
        closes = content.count("WIKI_SECTION_END")
        if opens != closes:
            logger.warning("WIKI_SECTION 标记不配对: {} 个开标记, {} 个闭标记", opens, closes)

        if not content.strip().startswith("---"):
            logger.warning("页面可能缺少 frontmatter: {}", spec.path)

        return PageResult(page_path=spec.path, success=True)

    # ── Prompt building ─────────────────────────────────────────────────────

    def _build_page_prompt(self, spec: PageSpec, style_guide: str) -> str:
        parts: list[str] = []

        parts.append(f"请为项目生成一个完整的 wiki 页面，写入文件：{spec.path}\n")

        if style_guide:
            parts.append(f"## 风格要求\n\n{style_guide}\n")

        parts.append(f"## 页面信息\n")
        parts.append(f"- 标题: {spec.title}")
        parts.append(f"- 标签: {', '.join(spec.tags)}")
        if spec.description:
            parts.append(f"- 描述: {spec.description}")
        parts.append("")

        parts.append("## 章节定义\n")
        for i, section in enumerate(spec.sections, 1):
            parts.append(f"### 章节 {i}: {section.id}")
            if section.description:
                parts.append(f"描述: {section.description}")

            # Resolve and read source files
            source_contents = self._read_sources(section)
            if source_contents:
                parts.append(f"\n以下是对应的源代码：\n")
                for fpath, fcontent in source_contents.items():
                    ext = os.path.splitext(fpath)[1]
                    parts.append(f"**{fpath}**:")
                    parts.append(f"```{ext.lstrip('.')}")
                    parts.append(fcontent[:6000])  # Limit per file
                    parts.append("```\n")
            else:
                parts.append("(未找到匹配的源文件，请根据章节描述生成内容)\n")

        parts.append("\n## 输出要求\n")
        parts.append("请使用 write 工具将生成的页面写入目标文件。")
        parts.append("页面必须包含 YAML 前导码 (--- ... ---)、WIKI_SECTION 标记、**source** 溯源行。")
        parts.append("每个章节至少包含一段正文说明，不要只有标题。")

        if spec.sections:
            parts.append(f"\n预期的章节标识符: {', '.join(s.id for s in spec.sections)}")

        return "\n".join(parts)

    # ── Source resolution ───────────────────────────────────────────────────

    def _read_sources(self, section: SectionSpec) -> dict[str, str]:
        """Resolve glob patterns and read source file contents.

        Returns {relative_path: content}.
        """
        result: dict[str, str] = {}
        if not section.source_files:
            return result

        for pattern in section.source_files:
            # glob relative to project root
            full_pattern = str(self._project_root / pattern)
            matches = glob.glob(full_pattern, recursive=True)
            for fpath in sorted(matches)[:5]:  # Max 5 files per section
                if not os.path.isfile(fpath):
                    continue
                rel = os.path.relpath(fpath, str(self._project_root)).replace("\\", "/")
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    result[rel] = content
                except Exception:
                    pass

        return result
