"""API key storage for wiki-agent — mirrors pi_coding_agent/core/auth_storage.py"""

from __future__ import annotations

import json
import os
from pathlib import Path


class AuthStorage:
    """Stores API keys on disk. Storage: ~/.pi/agent/auth.json"""

    AUTH_DIR = os.path.join(os.path.expanduser("~"), ".pi", "agent")
    AUTH_FILE = os.path.join(AUTH_DIR, "auth.json")

    def __init__(self) -> None:
        self._data: dict[str, object] = {}
        self._loaded = False
        self._runtime_overrides: dict[str, str] = {}

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
            self._loaded = True

    def _load(self) -> None:
        if os.path.exists(self.AUTH_FILE):
            try:
                with open(self.AUTH_FILE, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def _save(self) -> None:
        os.makedirs(self.AUTH_DIR, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(self.AUTH_FILE, flags, mode)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def set_runtime_override(self, provider: str, api_key: str) -> None:
        self._runtime_overrides[provider] = api_key

    def resolve_api_key(self, provider: str) -> str | None:
        if provider in self._runtime_overrides:
            return self._runtime_overrides[provider]
        self._ensure_loaded()
        stored = self._data.get(provider, {})
        if isinstance(stored, dict):
            return stored.get("api_key")
        from pi_ai.env_api_keys import get_env_api_key
        return get_env_api_key(provider)
