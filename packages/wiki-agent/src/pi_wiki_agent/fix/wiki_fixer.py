"""Wiki fixer — methods to repair quality issues found by WikiQualityChecker."""

from __future__ import annotations

import re
from pathlib import Path

from ..core.wiki_quality import QualityIssue, QualityReport
from ..logging import logger
from ..metadata import IndexEntry, WikiMetadata

# ── Patterns matching those in wiki_quality.py ─────────────────────────────
_SOURCE_LINE = re.compile(r"\*\*source\*\*:\[([^\]]*)\]\(file://([^)]*)\)")
_WIKI_SECTION_OPEN = re.compile(r"<!--\s*WIKI_SECTION:\s*(\S+)")


class WikiFixer:
    """Applies fixes for wiki quality issues.

    Each ``fix_*`` method corresponds to a check from WikiQualityChecker and
    accepts a single QualityIssue, returning whether the fix was applied.
    """

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.wiki_dir = self.project_root / ".wiki"
        self._metadata = WikiMetadata(self.wiki_dir)

    # ── helpers ───────────────────────────────────────────────────────────

    def _read_page(self, page: str) -> str:
        fp = self.wiki_dir / page
        return fp.read_text(encoding="utf-8") if fp.exists() else ""

    def _parse_sections(self, content: str) -> list[tuple[str, int]]:
        return [(m.group(1), content[: m.start()].count("\n") + 1)
                for m in _WIKI_SECTION_OPEN.finditer(content)]

    def _parse_source_links(self, content: str) -> list[str]:
        return [m.group(2) for m in _SOURCE_LINE.finditer(content)]

    def _source_links_for_section(self, content: str, section_id: str,
                                  next_line: int | None) -> list[str]:
        """Extract source links belonging to a specific section."""
        lines = content.split("\n")
        section_start = -1
        for i, line in enumerate(lines):
            m = _WIKI_SECTION_OPEN.search(line)
            if m and m.group(1) == section_id:
                section_start = i
                break
        if section_start == -1:
            return []

        end = next_line - 1 if next_line is not None else len(lines)
        section_text = "\n".join(lines[section_start:end])
        return self._parse_source_links(section_text)

    # ── P0: traceability fixes ────────────────────────────────────────────

    def fix_source_link_missing(self, issue: QualityIssue) -> bool:
        """Remove a broken **source** link line from a wiki page."""
        page = issue.page
        fp = self.wiki_dir / page
        if not fp.exists():
            return False

        broken_src = issue.message.split(": ", 1)[-1].strip()
        if not broken_src:
            return False

        content = fp.read_text(encoding="utf-8")
        pattern = re.compile(
            r"^" + re.escape("**source**:[") + r"[^\]]*" + re.escape("](file://")
            + re.escape(broken_src) + re.escape(")") + r"[ \t]*(\r?\n)?",
            re.MULTILINE,
        )
        new_content, count = pattern.subn("", content)
        if count == 0:
            return False

        fp.write_text(new_content, encoding="utf-8")
        logger.info("已从页面 %s 中移除 %d 条失效 source 链接", page, count)
        return True

    def fix_index_page_missing(self, issue: QualityIssue) -> bool:
        """Remove index entries whose wiki_page no longer exists."""
        page = issue.page
        data = self._metadata.load()
        before = len(data.index)
        data.index = [e for e in data.index if e.wiki_page != page]
        removed = before - len(data.index)
        self._metadata.save(data)
        logger.info("已从索引中移除 %d 条不存在页面的记录: %s", removed, page)
        return True

    def fix_index_source_missing(self, issue: QualityIssue) -> bool:
        """Remove index entries whose source file no longer exists."""
        broken_src = issue.message.split(": ", 1)[-1].strip()
        if not broken_src:
            return False

        data = self._metadata.load()
        before = len(data.index)
        data.index = [e for e in data.index if e.file != broken_src]
        removed = before - len(data.index)
        self._metadata.save(data)
        logger.info("已从索引中移除源文件 %s 的 %d 条记录", broken_src, removed)
        return True

    def fix_orphan_page(self, issue: QualityIssue) -> bool:
        """Add index entries for an orphan wiki page by scanning its sections
        and source links, then appending to repowiki-metadata.json."""
        page = issue.page
        content = self._read_page(page)
        if not content:
            logger.warning("无法读取页面内容: %s", page)
            return False

        sections = self._parse_sections(content)
        source_links = self._parse_source_links(content)

        if not source_links:
            # page has no source references — create a page-level entry only
            new_entries = [IndexEntry(file="", wiki_page=page, section_id="")]
        else:
            # map each section to its source links
            new_entries: list[IndexEntry] = []
            for idx, (sec_id, line_no) in enumerate(sections):
                next_line = sections[idx + 1][1] if idx + 1 < len(sections) else None
                sec_sources = self._source_links_for_section(content, sec_id, next_line)
                for src in sec_sources:
                    new_entries.append(IndexEntry(file=src, wiki_page=page, section_id=sec_id))
            # source links outside any section → page-level entries
            if not sections and source_links:
                for src in source_links:
                    new_entries.append(IndexEntry(file=src, wiki_page=page, section_id=""))

        data = self._metadata.load()
        existing_keys = {(e.file, e.wiki_page, e.section_id) for e in data.index}
        for entry in new_entries:
            key = (entry.file, entry.wiki_page, entry.section_id)
            if key not in existing_keys:
                data.index.append(entry)
                existing_keys.add(key)

        self._metadata.save(data)
        logger.info("已将孤立页面 %s 的 %d 条记录加入索引", page, len(new_entries))
        return True

    def fix_stale_index_entry(self, issue: QualityIssue) -> bool:
        """Remove index entries whose section_id no longer exists in the page."""
        page = issue.page
        section_id = issue.section
        data = self._metadata.load()
        before = len(data.index)
        data.index = [
            e for e in data.index
            if not (e.wiki_page == page and e.section_id == section_id)
        ]
        removed = before - len(data.index)
        self._metadata.save(data)
        logger.info("已从索引中移除页面 %s 章节 '%s' 的 %d 条记录", page, section_id, removed)
        return True

    # ── P1: freshness fixes ───────────────────────────────────────────────

    def fix_outdated_content(self, issue: QualityIssue) -> bool:
        """Trigger a re-generation of an outdated wiki page."""
        ...

    def fix_empty_section(self, issue: QualityIssue) -> bool:
        """Remove or regenerate an empty WIKI_SECTION."""
        ...

    def fix_duplicate_section(self, issue: QualityIssue) -> bool:
        """Deduplicate repeated WIKI_SECTION blocks in a page."""
        ...

    def fix_html_entities(self, issue: QualityIssue) -> bool:
        """Decode HTML entities back to literal characters."""
        ...

    # ── Dispatch ──────────────────────────────────────────────────────────

    _CHECK_TO_FIX: dict[str, str] = {
        "source_link_missing":      "fix_source_link_missing",
        "index_page_missing":      "fix_index_page_missing",
        "index_source_missing":    "fix_index_source_missing",
        "orphan_page":             "fix_orphan_page",
        "stale_index_entry":       "fix_stale_index_entry",
        "outdated_content":        "fix_outdated_content",
        "empty_section":           "fix_empty_section",
        "duplicate_section":       "fix_duplicate_section",
        "html_entity":             "fix_html_entities",
    }

    def fix_issue(self, issue: QualityIssue) -> bool:
        """Dispatch to the right fix method based on issue.check."""
        method_name = self._CHECK_TO_FIX.get(issue.check)
        if method_name is None:
            logger.warning("no fix method for check=%s", issue.check)
            return False
        fixer = getattr(self, method_name, None)
        if fixer is None:
            return False
        return fixer(issue)

    def fix_all(self, report: QualityReport) -> dict[str, bool]:
        """Run fixes for every issue in a quality report.

        Returns a dict mapping ``issue.check`` → success.
        """
        results: dict[str, bool] = {}
        for issue in report.issues:
            ok = self.fix_issue(issue)
            results[issue.check] = ok
        return results
