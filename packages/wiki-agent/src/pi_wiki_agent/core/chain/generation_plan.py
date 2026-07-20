"""Generation plan — data model for defining wiki structure to generate."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SectionSpec:
    """A single section within a wiki page."""
    id: str                            # WIKI_SECTION identifier
    description: str = ""              # What this section should cover
    source_files: list[str] = field(default_factory=list)  # Glob patterns to relevant source files


@dataclass
class PageSpec:
    """A wiki page to generate."""
    path: str                          # Relative path under .wiki/, e.g. "architecture.md"
    title: str = ""                    # Page title (frontmatter)
    tags: list[str] = field(default_factory=list)
    description: str = ""              # Page purpose, guides LLM content generation
    sections: list[SectionSpec] = field(default_factory=list)


@dataclass
class GenerationPlan:
    """Full wiki generation plan."""
    version: str = "1.0"
    style_guide: str = ""              # Global style instructions for all pages
    pages: list[PageSpec] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str | Path) -> GenerationPlan:
        """Load a generation plan from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        pages = []
        for p in data.get("pages", []):
            sections = []
            for s in p.get("sections", []):
                sections.append(SectionSpec(
                    id=s.get("id", ""),
                    description=s.get("description", ""),
                    source_files=s.get("source_files", []),
                ))
            pages.append(PageSpec(
                path=p.get("path", ""),
                title=p.get("title", ""),
                tags=p.get("tags", []),
                description=p.get("description", ""),
                sections=sections,
            ))

        return cls(
            version=data.get("version", "1.0"),
            style_guide=data.get("style_guide", ""),
            pages=pages,
        )

    @classmethod
    def load(cls, project_root: str | Path) -> GenerationPlan | None:
        """Load the generation-plan.json from a project's .wiki/ directory.

        Returns None if the file doesn't exist.
        """
        plan_path = Path(project_root) / ".wiki" / "generation-plan.json"
        if not plan_path.exists():
            return None
        return cls.from_json(plan_path)


def has_wiki_pages(project_root: str | Path) -> bool:
    """Check if a project has any wiki pages (excluding templates)."""
    wiki_dir = Path(project_root) / ".wiki"
    if not wiki_dir.exists():
        return False
    for root, dirs, files in os.walk(str(wiki_dir)):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if f.endswith(".md"):
                return True
    return False
