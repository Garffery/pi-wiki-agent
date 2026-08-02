"""
Checkpoint store for workflow resume — independent of the sandbox.

Usage:
    store = CheckpointStore("/project/.wiki/checkpoints", namespace="abc123")
    store.save("analysis", result)   # -> .wiki/checkpoints/abc123/analysis.json
    result = store.load("analysis")  # None if missing
    store.has("analysis")            # True/False
    store.clear("analysis")          # delete one key
    store.clear()                    # delete entire namespace
"""
from __future__ import annotations

import json
import os
from typing import Any


class CheckpointStore:
    """JSON-file-backed key-value store for workflow checkpoint/resume.

    Each workflow run is isolated by a namespace (typically the commit hash).
    File structure: <base_dir>/<namespace>/<key>.json
    """

    def __init__(self, base_dir: str, namespace: str = "default"):
        self.base_dir = base_dir
        self.namespace = namespace
        self._dir = os.path.join(base_dir, namespace)
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self._dir, f"{key}.json")

    def save(self, key: str, value: Any) -> None:
        with open(self._path(key), 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)

    def load(self, key: str) -> Any:
        path = self._path(key)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def has(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def clear(self, key: str | None = None) -> None:
        import shutil
        if key:
            path = self._path(key)
            if os.path.exists(path):
                os.remove(path)
        else:
            shutil.rmtree(self._dir, ignore_errors=True)
