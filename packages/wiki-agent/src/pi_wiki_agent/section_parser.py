"""Parse WIKI_SECTION markers and source links from wiki pages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from .logging import logger

_SECTION_OPEN = re.compile(r"<!--\s*WIKI_SECTION:\s*(.+?)\s*-->")
_SECTION_CLOSE = re.compile(r"<!--\s*WIKI_SECTION_END\s*-->")
_SOURCE_LINK = re.compile(r"\*\*source\*\*:\[(.+?)\]\(file://(.+?)\)")


class Section(NamedTuple):
    id: str
    heading: str
    sources: list[str]  # relative file paths
    start_line: int  # 0-indexed, after the open marker
    end_line: int  # 0-indexed, before the close marker


class WikiPage(NamedTuple):
    path: str  # relative to .wiki root
    sections: list[Section]


def parse_wiki_page(file_path: str | Path) -> WikiPage:
    """Parse a single wiki page, extracting all sections with their source mappings.

    Args:
        file_path: Path to the .md file.

    Returns:
        WikiPage with the file path and list of extracted sections.
    """
    file_path = Path(file_path)
    lines = file_path.read_text("utf-8").splitlines(keepends=False)
    page = _extract_sections(str(file_path), lines)
    logger.debug("解析 wiki 页面: {} → {} 个章节", file_path, len(page.sections))
    return page


def _extract_sections(path: str, lines: list[str]) -> WikiPage:
    sections: list[Section] = []
    current_section_id: str | None = None
    current_start: int | None = None
    pending_sources: list[str] = []
    heading: str = ""

    for i, line in enumerate(lines):
        # Check for section open
        m_open = _SECTION_OPEN.match(line)
        if m_open:
            current_section_id = m_open.group(1).strip()
            current_start = i + 1  # content starts on next line
            pending_sources = []
            heading = ""
            continue

        # Check for section close
        if _SECTION_CLOSE.match(line):
            if current_section_id is not None and current_start is not None:
                sections.append(Section(
                    id=current_section_id,
                    heading=heading,
                    sources=pending_sources,
                    start_line=current_start,
                    end_line=i,  # exclusive
                ))
            current_section_id = None
            current_start = None
            pending_sources = []
            heading = ""
            continue

        # Inside a section
        if current_section_id is not None:
            # Collect source links anywhere in the section
            for m_src in _SOURCE_LINK.finditer(line):
                source_file = m_src.group(2).strip()
                if source_file not in pending_sources:
                    pending_sources.append(source_file)

            # Capture the first heading as the section heading
            stripped = line.strip()
            if not heading and stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()

    return WikiPage(path=path, sections=sections)
