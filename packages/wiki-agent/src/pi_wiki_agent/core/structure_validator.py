"""Full-page wiki structure validator with programmatic auto-fix.

Reads the page once, runs checks and fixes in order, writes back if anything
was auto-fixed. Returns issues that require LLM intervention.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..metadata import WikiMetadata

_WIKI_LINK = re.compile(r"\[\[(.+?)\]\]")

# ── Regex patterns (consistent with section_parser.py) ─────────────────────
_SECTION_OPEN = re.compile(r"<!--\s*WIKI_SECTION:\s*(.+?)\s*-->")
_SECTION_CLOSE = re.compile(r"<!--\s*WIKI_SECTION_END\s*-->")
_SOURCE_LINE = re.compile(r"^\*\*source\*\*:\[.+?\]\(file://.+?\)$")
_HEADING = re.compile(r"^(#{1,6})\s")


@dataclass
class ValidationResult:
    """Result of validating a single wiki page."""

    page: str
    auto_fixed: list[str] = field(default_factory=list)
    needs_llm: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.auto_fixed or self.needs_llm)


class WikiStructureValidator:
    """Validate and auto-fix a wiki page's structural integrity.

    Reads the page once, applies programmatic fixes (marker pairing,
    frontmatter format, source links), writes back if changed, and collects
    remaining issues that require LLM understanding.
    """

    def __init__(self, wiki_root: str | Path, metadata: WikiMetadata | None = None) -> None:
        self._wiki_root = Path(wiki_root)
        self._metadata = metadata

    # ── Public API ────────────────────────────────────────────────────────────

    def validate_and_fix(self, page_path: str) -> ValidationResult:
        """Validate and auto-fix a single wiki page.

        Returns a ``ValidationResult`` with auto-fixed and LLM-level issues.
        Writes back to disk if any auto-fixes were applied.
        """
        result = ValidationResult(page=page_path)
        file_path = self._wiki_root / page_path

        if not file_path.exists():
            result.needs_llm.append(f"页面文件不存在: {page_path}")
            return result

        content = file_path.read_text("utf-8")

        # ── Phase 1: auto-fix (order matters) ────────────────────────────
        content, fm_fixes = self._fix_frontmatter(content)
        result.auto_fixed.extend(fm_fixes)

        content, marker_fixes = self._fix_section_markers(content)
        result.auto_fixed.extend(marker_fixes)

        content, source_fixes = self._fix_source_links(content, page_path)
        result.auto_fixed.extend(source_fixes)

        # Write back if any auto-fix was applied
        if result.auto_fixed:
            file_path.write_text(content, "utf-8")

        # ── Phase 2: detect issues requiring LLM ─────────────────────────
        result.needs_llm.extend(self._check_wiki_links(content))
        result.needs_llm.extend(self._check_heading_hierarchy(content))
        result.needs_llm.extend(self._check_missing_sections(content, page_path))

        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Auto-fix: frontmatter
    # ═══════════════════════════════════════════════════════════════════════════

    def _fix_frontmatter(self, content: str) -> tuple[str, list[str]]:
        """Ensure valid YAML frontmatter with required fields. Returns (content, fixes)."""
        fixes: list[str] = []

        if not content.startswith("---"):
            fixes.append("缺少 frontmatter，已添加默认值")
            frontmatter = self._default_frontmatter()
            content = frontmatter + "\n" + content
            return content, fixes

        # Find closing ---
        second = content.find("---", 3)
        if second == -1:
            fixes.append("frontmatter 格式损坏（无闭合 ---），已重建")
            body = content[3:].lstrip("\n")
            frontmatter = self._default_frontmatter()
            content = frontmatter + "\n" + body
            return content, fixes

        raw = content[3:second].strip()
        body = content[second + 3:].lstrip("\n")

        meta = self._parse_simple_yaml(raw)
        changed = False

        if "title" not in meta:
            # Derive from first H1 heading in body
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            meta["title"] = h1_match.group(1).strip() if h1_match else "Untitled"
            fixes.append("frontmatter 缺少 title，已从正文标题推断")
            changed = True

        if "date" not in meta:
            meta["date"] = date.today().isoformat()
            fixes.append("frontmatter 缺少 date，已设为今天")
            changed = True

        if "tags" not in meta:
            meta["tags"] = []
            fixes.append("frontmatter 缺少 tags，已设为空列表")
            changed = True

        if not changed:
            return content, fixes

        new_fm = self._serialize_frontmatter(meta)
        return new_fm + "\n" + body, fixes

    # ═══════════════════════════════════════════════════════════════════════════
    # Auto-fix: section markers
    # ═══════════════════════════════════════════════════════════════════════════

    def _fix_section_markers(self, content: str) -> tuple[str, list[str]]:
        """Fix WIKI_SECTION open/close marker pairing. Returns (content, fixes)."""
        lines = content.splitlines(keepends=True)
        fixes: list[str] = []
        stack: list[tuple[str, int]] = []  # [(section_id, line_index)]
        i = 0

        while i < len(lines):
            line = lines[i]
            m_open = _SECTION_OPEN.match(line.strip())
            m_close = _SECTION_CLOSE.match(line.strip())

            if m_open:
                section_id = m_open.group(1).strip()
                # Previous section unclosed → close it before this open
                if stack:
                    prev_id, prev_line = stack.pop()
                    lines.insert(i, "<!-- WIKI_SECTION_END -->\n")
                    fixes.append(f"第 {prev_line + 1} 行: section '{prev_id}' 缺少 WIKI_SECTION_END，已补上")
                    i += 1  # account for inserted line
                stack.append((section_id, i))
            elif m_close:
                if stack:
                    stack.pop()
                else:
                    # Orphan close marker → remove
                    fixes.append(f"第 {i + 1} 行: 孤立的 WIKI_SECTION_END，已移除")
                    lines[i] = ""
                    # Also remove trailing newline if the previous line became empty
                    # (keep it simple — just blank the line)

            i += 1

        # Close remaining unclosed sections
        for section_id, open_line in reversed(stack):
            lines.append("<!-- WIKI_SECTION_END -->\n")
            fixes.append(f"第 {open_line + 1} 行: section '{section_id}' 缺少 WIKI_SECTION_END，已补上")

        if fixes:
            return "".join(lines), fixes
        return content, fixes

    # ═══════════════════════════════════════════════════════════════════════════
    # Auto-fix: source links
    # ═══════════════════════════════════════════════════════════════════════════

    def _fix_source_links(self, content: str, page_path: str) -> tuple[str, list[str]]:
        """Ensure each section has correct source links. Returns (content, fixes)."""
        expected = self._expected_sources(page_path)  # {section_id: [file_paths]}
        if not expected:
            return content, []

        lines = content.splitlines(keepends=True)
        fixes: list[str] = []
        in_section: str | None = None
        section_has_source: set[str] = set()
        heading_line: int | None = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            m_open = _SECTION_OPEN.match(stripped)
            m_close = _SECTION_CLOSE.match(stripped)

            if m_open:
                in_section = m_open.group(1).strip()
                heading_line = None
            elif m_close:
                # End of section — check if sources needed but missing
                if in_section and in_section in expected and in_section not in section_has_source:
                    source_files = expected[in_section]
                    source_lines = [
                        f"**source**:[{f}](file://{f})\n" for f in source_files
                    ]
                    # Insert after the section heading, or after the open marker
                    insert_at = heading_line + 1 if heading_line is not None else i
                    for j, sl in enumerate(source_lines):
                        lines.insert(insert_at + j, sl)
                    fixes.append(
                        f"section '{in_section}': 缺少 source 溯源行，已从 metadata 补回 ({', '.join(source_files)})"
                    )
                in_section = None
                heading_line = None
            elif in_section:
                if _SOURCE_LINE.match(stripped):
                    section_has_source.add(in_section)
                elif _HEADING.match(stripped) and heading_line is None:
                    heading_line = i

        if fixes:
            return "".join(lines), fixes
        return content, fixes

    # ═══════════════════════════════════════════════════════════════════════════
    # LLM-level: wiki links
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_wiki_links(self, content: str) -> list[str]:
        """Check [[wiki links]] point to existing .md files.

        Handles extended syntax: ``[[page|alias]]`` and ``[[page#anchor]]``.
        """
        issues: list[str] = []
        seen: set[str] = set()

        for m in _WIKI_LINK.finditer(content):
            raw = m.group(1).strip()
            # Strip alias ([[page|display]])
            target = raw.split("|")[0].strip()
            # Strip anchor ([[page#section]])
            target = target.split("#")[0].strip()
            if not target or target in seen:
                continue
            seen.add(target)

            target_file = self._wiki_root / f"{target}.md"
            if not target_file.exists():
                line_no = content[: m.start()].count("\n") + 1
                issues.append(f"第 {line_no} 行: 断裂链接 [[{raw}]] → {target}.md 不存在")

        return issues

    # ═══════════════════════════════════════════════════════════════════════════
    # LLM-level: heading hierarchy
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_heading_hierarchy(self, content: str) -> list[str]:
        """Check that heading levels don't skip (H2 → H4 without H3)."""
        issues: list[str] = []
        prev_level: int = 1  # H1 is the page title

        for i, line in enumerate(content.splitlines()):
            m = _HEADING.match(line)
            if not m:
                continue
            level = len(m.group(1))
            if level > prev_level + 1:
                issues.append(
                    f"第 {i + 1} 行: 标题层级跳跃 H{prev_level} → H{level}（跳过了 H{level - 1}）"
                )
            prev_level = level

        return issues

    # ═══════════════════════════════════════════════════════════════════════════
    # LLM-level: missing sections (metadata says should exist, but page doesn't have)
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_missing_sections(self, content: str, page_path: str) -> list[str]:
        """Detect sections in metadata index but missing from the page."""
        if self._metadata is None:
            return []

        entries = self._metadata.query_by_wiki_page(page_path)
        expected_ids = {e.section_id for e in entries}
        found_ids = set(_SECTION_OPEN.findall(content))
        missing = expected_ids - found_ids

        if not missing:
            return []

        issues: list[str] = []
        for sid in sorted(missing):
            # Show which source files map to this missing section
            sources = [e.file for e in entries if e.section_id == sid]
            issues.append(f"缺失 section '{sid}'（metadata 索引到源文件: {', '.join(sources)}）")
        return issues

    # ═══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _expected_sources(self, page_path: str) -> dict[str, list[str]]:
        """Get expected source files per section from metadata, or {} if unavailable."""
        if self._metadata is None:
            return {}
        entries = self._metadata.query_by_wiki_page(page_path)
        result: dict[str, list[str]] = {}
        for e in entries:
            result.setdefault(e.section_id, []).append(e.file)
        return result

    @staticmethod
    def _default_frontmatter() -> str:
        today = date.today().isoformat()
        return f"---\ntitle: Untitled\ndate: {today}\ntags: []\n---"

    @staticmethod
    def _parse_simple_yaml(raw: str) -> dict:
        """Simple YAML parser for frontmatter (no pyyaml dependency for this module)."""
        result: dict = {}
        for line in raw.strip().split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip("\"'")
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    val = [v.strip().strip("\"'") for v in inner.split(",") if v.strip()]
                result[key] = val
        return result

    @staticmethod
    def _serialize_frontmatter(meta: dict) -> str:
        lines = ["---"]
        for key, value in meta.items():
            if isinstance(value, list):
                items = ", ".join(str(v) for v in value)
                lines.append(f"{key}: [{items}]")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)
