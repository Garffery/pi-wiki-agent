"""Wiki quality checker — traceability (P0) and freshness (P1) checks.

Walks .wiki/**/*.md pages and the reverse index (repowiki-metadata.json)
to detect broken source links, stale index entries, outdated content, etc.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..logging import logger

# ── Source link pattern: **source**:[filename](file://path) ──────────────────
_SOURCE_LINE = re.compile(r"\*\*source\*\*:\[([^\]]*)\]\(file://([^)]*)\)")

# ── HTML entity residues ────────────────────────────────────────────────────
_HTML_ENTITY = re.compile(r"&(?:lt|gt|amp|quot|nbsp);")

# ── WIKI_SECTION pattern ────────────────────────────────────────────────────
_WIKI_SECTION_OPEN = re.compile(r"<!--\s*WIKI_SECTION:\s*(\S+)")


# ── Data models ─────────────────────────────────────────────────────────────

@dataclass
class QualityIssue:
    page: str                     # wiki page path (relative to .wiki/)
    section: str | None = None    # section id, None if page-level
    category: str = ""            # "traceability" | "freshness"
    severity: str = "warning"     # "error" | "warning" | "info"
    check: str = ""               # check name e.g. "source_link_stale"
    message: str = ""             # human-readable
    detail: str | None = None     # extra context


@dataclass
class QualityReport:
    project_path: str = ""
    checked_at: str = ""
    total_pages: int = 0
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    issues: list[QualityIssue] = field(default_factory=list)


# ── Checker ─────────────────────────────────────────────────────────────────

class WikiQualityChecker:
    """Runs traceability (P0) and freshness (P1) checks on a wiki project."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._wiki_root = self._project_root / ".wiki"

    # ── Public ──────────────────────────────────────────────────────────────

    def run_checks(self) -> QualityReport:
        """Run all P0+P1 checks and return a QualityReport."""
        pages = self._list_wiki_pages()
        index_data = self._load_index()

        report = QualityReport(
            project_path=str(self._project_root),
            checked_at=datetime.now(timezone.utc).isoformat(),
            total_pages=len(pages),
        )

        # ── P0: Traceability ────────────────────────────────────────────────
        self._check_source_links_exist(pages, report)
        self._check_index_pages_exist(index_data, report)
        self._check_index_sources_exist(index_data, report)
        self._check_orphan_pages(pages, index_data, report)
        self._check_stale_index_entries(pages, index_data, report)

        # ── P1: Freshness ───────────────────────────────────────────────────
        self._check_outdated_content(pages, index_data, report)
        self._check_empty_sections(pages, report)
        self._check_duplicate_sections(pages, report)
        self._check_html_entities(pages, report)

        report.total_issues = len(report.issues)
        report.errors = sum(1 for i in report.issues if i.severity == "error")
        report.warnings = sum(1 for i in report.issues if i.severity == "warning")

        logger.info(
            "质量检查完成: {} 页面, {} 问题 ({} error, {} warning)",
            report.total_pages, report.total_issues, report.errors, report.warnings,
        )
        return report

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _list_wiki_pages(self) -> list[str]:
        """List all .md files under .wiki/, relative to .wiki/.

        Skips files/directories starting with _ (templates, internal files).
        """
        pages: list[str] = []
        for root, dirs, files in os.walk(self._wiki_root):
            # Skip _ prefixed directories
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for f in files:
                if f.endswith(".md"):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, str(self._wiki_root)).replace("\\", "/")
                    pages.append(rel)
        return sorted(pages)

    def _load_index(self) -> list[dict[str, str]]:
        """Load repowiki-metadata.json entries."""
        path = self._wiki_root / "repowiki-metadata.json"
        if not path.exists():
            return []
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("index", [])
        except Exception as e:
            logger.warning("无法加载反向索引: {}", e)
            return []

    def _read_page_content(self, page: str) -> str:
        """Read a wiki page's raw content."""
        fp = self._wiki_root / page
        try:
            return fp.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _source_exists(self, path: str) -> bool:
        """Check if a source file referenced via file:// exists."""
        full = self._project_root / path
        return full.exists()

    def _source_mtime(self, path: str) -> float | None:
        """Get modification time of a source file, or None."""
        full = self._project_root / path
        if full.exists():
            return full.stat().st_mtime
        return None

    def _wiki_mtime(self, page: str) -> float | None:
        """Get modification time of a wiki page, or None."""
        fp = self._wiki_root / page
        if fp.exists():
            return fp.stat().st_mtime
        return None

    def _parse_sections(self, content: str) -> list[tuple[str, int]]:
        """Find all WIKI_SECTION markers and return [(section_id, line_number), ...]."""
        return [(m.group(1), content[:m.start()].count("\n") + 1)
                for m in _WIKI_SECTION_OPEN.finditer(content)]

    def _parse_source_links(self, content: str) -> list[str]:
        """Extract source file paths from **source**:[...](file://path) lines."""
        return [m.group(2) for m in _SOURCE_LINE.finditer(content)]

    # ═══ P0: Traceability checks ═══════════════════════════════════════════

    def _check_source_links_exist(self, pages: list[str], report: QualityReport) -> None:
        """Check that every **source**:[...](file://path) points to an existing file."""
        for page in pages:
            content = self._read_page_content(page)
            sources = self._parse_source_links(content)
            for src in sources:
                if not self._source_exists(src):
                    report.issues.append(QualityIssue(
                        page=page,
                        category="traceability",
                        severity="error",
                        check="source_link_missing",
                        message=f"溯源链接指向不存在的文件: {src}",
                    ))

    def _check_index_pages_exist(self, index: list[dict], report: QualityReport) -> None:
        """Check that every index entry's wiki_page points to an existing .md file."""
        seen: set[str] = set()
        for entry in index:
            page = entry.get("wiki_page", "")
            if page and page not in seen:
                seen.add(page)
                fp = self._wiki_root / page
                if not fp.exists():
                    report.issues.append(QualityIssue(
                        page=page,
                        category="traceability",
                        severity="error",
                        check="index_page_missing",
                        message="反向索引指向不存在的 wiki 页面",
                    ))

    def _check_index_sources_exist(self, index: list[dict], report: QualityReport) -> None:
        """Check that every index entry's source file exists."""
        seen: set[str] = set()
        for entry in index:
            src = entry.get("file", "")
            if src and src not in seen:
                seen.add(src)
                if not self._source_exists(src):
                    report.issues.append(QualityIssue(
                        page=entry.get("wiki_page", "?"),
                        section=entry.get("section_id"),
                        category="traceability",
                        severity="error",
                        check="index_source_missing",
                        message=f"反向索引指向不存在的源文件: {src}",
                    ))

    def _check_orphan_pages(self, pages: list[str], index: list[dict], report: QualityReport) -> None:
        """Flag wiki pages that are not referenced in the reverse index."""
        indexed_pages = {e.get("wiki_page", "") for e in index}
        for page in pages:
            if page not in indexed_pages:
                report.issues.append(QualityIssue(
                    page=page,
                    category="traceability",
                    severity="warning",
                    check="orphan_page",
                    message="此页面不在反向索引中，可能无法被代码变更自动触发更新",
                ))

    def _check_stale_index_entries(self, pages: list[str], index: list[dict], report: QualityReport) -> None:
        """Flag index entries whose section no longer exists in the wiki page."""
        page_sections: dict[str, set[str]] = {}
        for page in pages:
            content = self._read_page_content(page)
            page_sections[page] = {s[0] for s in self._parse_sections(content)}

        for entry in index:
            page = entry.get("wiki_page", "")
            section_id = entry.get("section_id", "")
            if page in page_sections and section_id not in page_sections.get(page, set()):
                report.issues.append(QualityIssue(
                    page=page,
                    section=section_id,
                    category="traceability",
                    severity="warning",
                    check="stale_index_entry",
                    message=f"反向索引中的章节 '{section_id}' 在页面中已不存在",
                ))

    # ═══ P1: Freshness checks ═══════════════════════════════════════════════

    def _check_outdated_content(self, pages: list[str], index: list[dict],
                                 report: QualityReport) -> None:
        """Check if source files are newer than wiki pages (potential staleness).

        If any source file linked from a page was modified after the last time
        the wiki page was saved, flag it.
        """
        for page in pages:
            content = self._read_page_content(page)
            sources = self._parse_source_links(content)
            wiki_mtime = self._wiki_mtime(page)
            if not wiki_mtime:
                continue

            stale_sources: list[str] = []
            for src in sources:
                src_mtime = self._source_mtime(src)
                if src_mtime and src_mtime > wiki_mtime:
                    stale_sources.append(src)

            if stale_sources:
                report.issues.append(QualityIssue(
                    page=page,
                    category="freshness",
                    severity="warning",
                    check="outdated_content",
                    message=f"以下源文件在 wiki 更新后又被修改: {', '.join(stale_sources[:3])}" +
                            (f" (+{len(stale_sources) - 3} 个)" if len(stale_sources) > 3 else ""),
                ))

    def _check_empty_sections(self, pages: list[str], report: QualityReport) -> None:
        """Flag WIKI_SECTION blocks with no meaningful content."""
        for page in pages:
            content = self._read_page_content(page)
            # Split by WIKI_SECTION markers and check content between open/close
            blocks = re.split(r"<!--\s*WIKI_SECTION(?:_END)?[^>]*-->", content)
            # The blocks alternate: ...(open) content1 (close) ...(open) content2 (close)...
            # Skip until first OPEN, then check alternating blocks
            sections = self._parse_sections(content)
            if not sections:
                continue

            # Find content between each OPEN and its matching CLOSE
            lines = content.split("\n")
            in_section = None
            empty_sections: list[str] = []

            for i, line in enumerate(lines, 1):
                open_m = _WIKI_SECTION_OPEN.search(line)
                is_close = "WIKI_SECTION_END" in line

                if open_m and not is_close:
                    in_section = (open_m.group(1), i)
                elif is_close and in_section:
                    sid, start = in_section
                    end = i
                    # Content between start+1 and end-1
                    body_lines = [l.strip() for l in lines[start:end-1]]
                    # Remove heading lines (## etc), source lines, blank lines
                    meaningful = [
                        l for l in body_lines
                        if l and not l.startswith("#") and not l.startswith("**source**")
                    ]
                    if not meaningful:
                        empty_sections.append(sid)
                    in_section = None

            for sid in empty_sections:
                report.issues.append(QualityIssue(
                    page=page,
                    section=sid,
                    category="freshness",
                    severity="warning",
                    check="empty_section",
                    message=f"章节 '{sid}' 只有标题没有正文",
                ))

    def _check_duplicate_sections(self, pages: list[str], report: QualityReport) -> None:
        """Flag pages with duplicate WIKI_SECTION names."""
        for page in pages:
            content = self._read_page_content(page)
            section_ids = [s[0] for s in self._parse_sections(content)]
            seen: set[str] = set()
            dups: set[str] = set()
            for sid in section_ids:
                if sid in seen:
                    dups.add(sid)
                seen.add(sid)
            for sid in dups:
                report.issues.append(QualityIssue(
                    page=page,
                    section=sid,
                    category="freshness",
                    severity="error",
                    check="duplicate_section",
                    message=f"章节名 '{sid}' 在页面中重复出现",
                ))

    def _check_html_entities(self, pages: list[str], report: QualityReport) -> None:
        """Flag HTML entities (&lt; &gt; &amp; etc.) that may be LLM artifacts."""
        for page in pages:
            raw = self._read_page_content(page)
            # Only check body (skip frontmatter)
            parts = raw.split("---", 2)
            body = parts[2] if len(parts) >= 3 else raw
            matches = _HTML_ENTITY.findall(body)
            if matches:
                report.issues.append(QualityIssue(
                    page=page,
                    category="freshness",
                    severity="info",
                    check="html_entities",
                    message=f"正文中发现 {len(matches)} 处 HTML 实体残留 (如 &lt; &gt; &amp;)，可能是 LLM 误转义",
                ))
