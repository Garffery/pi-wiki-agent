"""Indexer — scan .wiki directory and build repowiki-metadata.json."""

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
    """Scan wiki pages and build/maintain the reverse index."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._wiki_root = self._project_root / ".wiki"
        self._metadata = WikiMetadata(self._wiki_root)

    @property
    def wiki_root(self) -> Path:
        return self._wiki_root

    @property
    def metadata(self) -> WikiMetadata:
        return self._metadata

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/")

    def full_rebuild(self) -> list[IndexEntry]:
        """Scan all wiki pages and rebuild the entire index."""
        entries: list[IndexEntry] = []
        for md_file in sorted(self._wiki_root.glob("**/*.md")):
            rel_path = self._norm(str(md_file.relative_to(self._wiki_root)))
            page = parse_wiki_page(md_file)
            for section in page.sections:
                for source in section.sources:
                    entries.append(IndexEntry(
                        file=source,
                        wiki_page=rel_path,
                        section_id=section.id,
                    ))
        self._metadata.rebuild(entries)
        logger.info("索引重建完成: {} 个条目, {} 个 wiki 页面", len(entries), len({e.wiki_page for e in entries}))
        return entries

    def get_affected_sections(self, changed_files: list[str]) -> dict[str, list[IndexEntry]]:
        """Given changed source files from a VCS commit, return wiki sections that need updating.

        Args:
            changed_files: List of file paths relative to project root (e.g. ['src/taskman/cli.py']).

        Returns:
            {wiki_page: [IndexEntry, ...]} grouped by wiki page, ordered by file then section.
        """
        changed = [self._norm(f) for f in changed_files]
        entries = self._metadata.query_by_files(changed)
        result: dict[str, list[IndexEntry]] = {}
        for entry in entries:
            result.setdefault(entry.wiki_page, []).append(entry)
        logger.debug("get_affected_sections: files={} matched={} pages={}", changed_files, len(entries), len(result))
        return result

    def update_page(self, wiki_page_rel: str) -> list[IndexEntry]:
        """Re-index a single wiki page and update its entries in the metadata.

        Returns the new entries for this page.
        """
        wiki_page_rel = self._norm(wiki_page_rel)
        md_file = self._wiki_root / wiki_page_rel
        entries: list[IndexEntry] = []
        if md_file.exists():
            page = parse_wiki_page(md_file)
            for section in page.sections:
                for source in section.sources:
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
