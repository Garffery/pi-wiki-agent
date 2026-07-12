"""Manage repowiki-metadata.json — the reverse index from source files to wiki sections."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class IndexEntry(BaseModel):
    file: str       # source file path relative to project root
    wiki_page: str  # wiki page path relative to .wiki
    section_id: str # WIKI_SECTION name


class RepoWikiMetadata(BaseModel):
    schema_version: str = "1.0"
    update_at: str = ""
    index: list[IndexEntry] = []


class WikiMetadata:
    """Read/write/query repowiki-metadata.json."""

    def __init__(self, wiki_root: str | Path) -> None:
        self._wiki_root = Path(wiki_root)
        self._metadata_path = self._wiki_root / "repowiki-metadata.json"

    def load(self) -> RepoWikiMetadata:
        """Load metadata from disk."""
        if not self._metadata_path.exists():
            return RepoWikiMetadata()
        raw = json.loads(self._metadata_path.read_text("utf-8"))
        return RepoWikiMetadata(**raw)

    def save(self, data: RepoWikiMetadata) -> None:
        """Save metadata to disk with updated timestamp."""
        data.update_at = datetime.now().isoformat(timespec="seconds")
        self._metadata_path.write_text(
            json.dumps(data.model_dump(), indent=2, ensure_ascii=False, default=str),
            "utf-8",
        )

    def query_by_files(self, changed_files: list[str]) -> list[IndexEntry]:
        """Given a list of changed source files, return all affected wiki sections."""
        data = self.load()
        changed = set(changed_files)
        result: list[IndexEntry] = []
        for entry in data.index:
            if entry.file in changed:
                result.append(entry)
        return result

    def query_by_wiki_page(self, wiki_page: str) -> list[IndexEntry]:
        """Given a wiki page, return all source files it references."""
        data = self.load()
        return [e for e in data.index if e.wiki_page == wiki_page]

    def replace_file_entries(self, file: str, new_entries: list[IndexEntry]) -> None:
        """Replace all index entries for a given source file."""
        data = self.load()
        data.index = [e for e in data.index if e.file != file]
        data.index.extend(new_entries)
        self.save(data)

    def rebuild(self, entries: list[IndexEntry]) -> None:
        """Fully rebuild the index from a list of entries."""
        data = RepoWikiMetadata(index=entries)
        self.save(data)
