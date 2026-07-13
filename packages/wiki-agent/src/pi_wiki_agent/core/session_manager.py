"""Session manager for wiki-agent — mirrors pi_coding_agent/core/session_manager.py"""

from __future__ import annotations

from pathlib import Path

from pi_coding_agent.core.session_manager import SessionManager as _BaseSessionManager


class SessionManager(_BaseSessionManager):
    """Wiki-aware session manager that adds wiki-specific session tracking.

    Wraps the coding-agent SessionManager to track wiki sync metadata
    (modified pages, commit hash, sync status) alongside base session data.
    """

    @classmethod
    def create(
        cls,
        cwd: str,
        session_dir: str | None = None,
        parent_session: str | None = None,
    ) -> SessionManager:
        base = _BaseSessionManager.create(cwd=cwd, session_dir=session_dir, parent_session=parent_session)
        base.__class__ = cls
        return base

    @classmethod
    def create_in_memory(cls) -> SessionManager:
        base = _BaseSessionManager.create_in_memory()
        base.__class__ = cls
        return base

    def mark_wiki_sync(self, commit_rev: str, pages_modified: list[str]) -> None:
        """Record a wiki sync operation in the session."""
        self.append_metadata({
            "type": "wiki_sync",
            "commit_revision": commit_rev,
            "pages_modified": pages_modified,
        })

    def get_wiki_syncs(self) -> list[dict]:
        """Get all wiki sync operations recorded in this session."""
        meta = self.get_metadata() or {}
        entries = meta.get("wiki_syncs", [])
        return entries if isinstance(entries, list) else []
