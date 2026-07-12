"""Settings management for wiki-agent — mirrors pi_coding_agent/core/settings_manager.py"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from pi_coding_agent.core.settings_manager import SettingsManager as _BaseSettingsManager, Settings as _BaseSettings


@dataclass
class WikiSettings:
    """Wiki-agent specific settings."""
    default_model: str = ""
    default_provider: str = "deepseek"
    auto_sync: bool = False
    sync_on_commit: bool = True
    commit_watch_interval: int = 30


class SettingsManager(_BaseSettingsManager):
    """Wiki-aware settings manager that extends the coding-agent settings manager.

    Adds wiki-specific settings on top of the base settings.
    """

    @classmethod
    def create(cls, cwd: str | None = None, agent_dir: str | None = None) -> SettingsManager:
        if agent_dir is None:
            from ..config import get_agent_dir
            agent_dir = get_agent_dir()
        mgr = cls()
        mgr._wiki_settings = WikiSettings()
        base = _BaseSettingsManager.create(cwd=cwd, agent_dir=agent_dir)
        mgr._base = base
        return mgr

    @classmethod
    def in_memory(cls) -> SettingsManager:
        mgr = cls()
        mgr._wiki_settings = WikiSettings()
        mgr._base = _BaseSettingsManager.in_memory()
        return mgr

    def get_wiki(self) -> WikiSettings:
        return self._wiki_settings

    def _load_wiki_settings(self) -> None:
        try:
            from ..config import get_settings_path
            path = get_settings_path()
            if os.path.exists(path):
                data = json.loads(open(path, encoding="utf-8").read())
                wiki_data = data.get("wiki", {})
                for k, v in wiki_data.items():
                    if hasattr(self._wiki_settings, k):
                        setattr(self._wiki_settings, k, v)
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        if hasattr(self._base, name):
            return getattr(self._base, name)
        raise AttributeError(name)
