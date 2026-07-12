"""VCS monitor abstract base class and CommitInfo data model."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..logging import logger

STATE_FILE = ".vcs-state.json"


@dataclass
class CommitInfo:
    """A single VCS commit with extracted change information."""

    revision: str
    message: str = ""
    author: str = ""
    timestamp: str = ""  # ISO 8601
    files: list[str] = field(default_factory=list)  # relative paths, / separator
    diff: str = ""  # unified diff, populated on demand


class VCSMonitor(ABC):
    """Abstract base for VCS monitors.

    Shared by both push (hook) and poll (timer) paths: both use the same
    get_commit() + mark_processed() flow, sharing one state file to prevent
    duplicate processing.
    """

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        wiki_root = self._project_root / ".wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        self._state_path = wiki_root / STATE_FILE
        self._state = self._load_state()

    @property
    def project_root(self) -> Path:
        return self._project_root

    # ── Public API ──────────────────────────────────────────────────────

    @abstractmethod
    async def poll(self) -> list[CommitInfo]:
        """Return new commits since the last marked revision (diff not populated).

        Used by the polling path. Returns an empty list if no new commits.
        """
        ...

    @abstractmethod
    async def get_commit(self, revision: str) -> CommitInfo:
        """Fetch full details (including diff) for a single revision.

        Used by both the hook path (single commit) and the polling path
        (iterate over poll() results to load diffs).
        """
        ...

    async def mark_processed(self, revision: str) -> None:
        """Record a revision as processed so poll() skips it next time."""
        self._state["last_revision"] = revision
        self._state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False), "utf-8"
        )
        logger.debug("标记已处理: revision={}", revision[:12])

    def get_last_revision(self) -> str:
        """Return the last processed revision, or empty string if none."""
        return self._state.get("last_revision", "")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text("utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return {"vcs": "", "last_revision": "", "updated_at": ""}

    @staticmethod
    def _norm_path(path: str) -> str:
        return path.strip().replace("\\", "/")


def create_monitor(project_root: str | Path) -> VCSMonitor:
    """Auto-detect VCS type and return the appropriate monitor instance."""
    root = Path(project_root)
    if (root / ".git").exists():
        from .git import GitMonitor
        logger.info("检测到 Git 仓库: {}", root)
        return GitMonitor(root)
    if (root / ".svn").exists():
        from .svn import SVNMonitor
        logger.info("检测到 SVN 仓库: {}", root)
        return SVNMonitor(root)
    raise FileNotFoundError(f"未找到 .git 或 .svn 目录: {root}")
