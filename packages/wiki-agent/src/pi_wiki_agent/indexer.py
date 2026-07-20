"""Indexer — scan .wiki directory and build repowiki-metadata.json.

Built-in commit-filter integration: any code using WikiIndexer automatically
respects per-project filter rules (``.wiki/filter.json``).  Filtered source
files are excluded from the index and from affected-section queries, so
front-end lists and sync pipelines stay consistent without extra work.
"""

from __future__ import annotations

from pathlib import Path

from .logging import logger

try:
    from .metadata import IndexEntry, WikiMetadata
    from .section_parser import parse_wiki_page
except ImportError:
    from metadata import IndexEntry, WikiMetadata
    from section_parser import parse_wiki_page


class WikiIndexer:
    """Scan wiki pages and build/maintain the reverse index.

    A per-project ``FilterManager`` is created internally so that every
    index operation respects the configured commit filters automatically.
    """

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._wiki_root = self._project_root / ".wiki"
        self._metadata = WikiMetadata(self._wiki_root)

        # ── Built-in filter integration ──────────────────────────────────
        from .filter import FilterManager
        self._filter = FilterManager(self._project_root)

    @property
    def wiki_root(self) -> Path:
        return self._wiki_root

    @property
    def metadata(self) -> WikiMetadata:
        return self._metadata

    @property
    def filter(self):
        """Expose the filter manager for rule CRUD at the API layer."""
        return self._filter

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/")

    # ── Index operations (all filter-aware) ──────────────────────────────

    def full_rebuild(self) -> list[IndexEntry]:
        """Scan all wiki pages and rebuild the entire index.

        Source-file entries that match path filters are excluded so they
        never surface in affected-section queries.
        """
        entries: list[IndexEntry] = []
        for md_file in sorted(self._wiki_root.glob("**/*.md")):
            rel_path = self._norm(str(md_file.relative_to(self._wiki_root)))
            page = parse_wiki_page(md_file)
            for section in page.sections:
                for source in section.sources:
                    if self._filter.is_path_excluded(source):
                        continue
                    entries.append(IndexEntry(
                        file=source,
                        wiki_page=rel_path,
                        section_id=section.id,
                    ))
        self._metadata.rebuild(entries)
        logger.info("索引重建完成: {} 个条目, {} 个 wiki 页面 (过滤掉了被排除的源文件)",
                     len(entries), len({e.wiki_page for e in entries}))
        return entries

    def get_affected_sections(self, changed_files: list[str]) -> dict[str, list[IndexEntry]]:
        """Return wiki sections affected by *changed_files*, respecting filters.

        Commit-message rules are NOT evaluated here — the caller decides
        whether to skip an entire commit.  Only path-based file filtering
        is applied.

        Returns:
            ``{wiki_page: [IndexEntry, ...]}`` grouped by wiki page.
        """
        filtered = self._filter.filter_files(changed_files)
        if not filtered:
            return {}
        changed = [self._norm(f) for f in filtered]
        entries = self._metadata.query_by_files(changed)
        result: dict[str, list[IndexEntry]] = {}
        for entry in entries:
            result.setdefault(entry.wiki_page, []).append(entry)
        logger.debug("get_affected_sections: files={} matched={} pages={}",
                     changed_files, len(entries), len(result))
        return result

    def update_page(self, wiki_page_rel: str) -> list[IndexEntry]:
        """Re-index a single wiki page, excluding filter-blocked source files.

        Returns the new entries for this page.
        """
        wiki_page_rel = self._norm(wiki_page_rel)
        md_file = self._wiki_root / wiki_page_rel
        entries: list[IndexEntry] = []
        if md_file.exists():
            page = parse_wiki_page(md_file)
            for section in page.sections:
                for source in section.sources:
                    if self._filter.is_path_excluded(source):
                        continue
                    entries.append(IndexEntry(
                        file=source,
                        wiki_page=wiki_page_rel,
                        section_id=section.id,
                    ))

        # Remove old entries for this page and insert new ones
        data = self._metadata.load()
        data.index = [e for e in data.index if e.wiki_page != wiki_page_rel]
        data.index.extend(entries)
        self._metadata.save(data)
        return entries
