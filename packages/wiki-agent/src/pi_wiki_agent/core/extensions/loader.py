"""Extension discovery and loading — mirrors pi_coding_agent/core/extensions/loader.py"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from ...logging import logger
from .types import Extension, ToolDefinition

_EXTENSION_PATHS = [
    os.path.join(os.path.expanduser("~"), ".pi-wiki-agent", "extensions"),
]


def _load_py_module(path: str) -> Any | None:
    """Load a Python module from a .py file."""
    try:
        name = f"wiki_ext_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        logger.warning("加载扩展模块失败: path={} err={}", path, e)
        return None


def _invoke_factory(mod: Any) -> Extension | None:
    """Try to invoke extension_factory(api) or activate(api) from the module."""
    for attr in ("extension_factory", "activate", "default"):
        fn = getattr(mod, attr, None)
        if callable(fn):
            ext = Extension(resolved_path=getattr(mod, "__file__", ""))
            api = _ExtensionAPI(ext)
            try:
                result = fn(api)
            except Exception:
                result = None
            if isinstance(result, Extension):
                return result
            # Return the api-built extension even if factory returned None
            return ext
    return None


class _ExtensionAPI:
    """Minimal API passed to extension_factory(api)."""

    def __init__(self, ext: Extension) -> None:
        self._ext = ext

    def on(self, event_type: str, handler) -> None:
        if event_type not in self._ext.handlers:
            self._ext.handlers[event_type] = []
        self._ext.handlers[event_type].append(handler)

    def register_tool(self, name: str, description: str, parameters: dict, execute, *, label: str = "", **kwargs) -> None:
        self._ext.tools[name] = ToolDefinition(
            name=name, label=label or name, description=description,
            parameters=parameters, execute=execute,
        )

    def register_command(self, name: str, description: str, handler) -> None:
        self._ext.commands[name] = handler


def discover_extensions(extra_paths: list[str] | None = None) -> list[Extension]:
    """Discover and load all extensions from configured paths."""
    extensions: list[Extension] = []
    search_paths = list(_EXTENSION_PATHS)
    if extra_paths:
        search_paths.extend(extra_paths)

    for base_dir in search_paths:
        base = Path(base_dir)
        if not base.exists():
            continue

        # Single .py files
        for py_file in sorted(base.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            mod = _load_py_module(str(py_file))
            if mod:
                result = _invoke_factory(mod)
                if isinstance(result, Extension):
                    extensions.append(result)

        # Subdirectories (package extensions)
        for pkg_dir in sorted(base.glob("*/")):
            init = pkg_dir / "__init__.py"
            if not init.exists():
                continue
            mod = _load_py_module(str(init))
            if mod:
                result = _invoke_factory(mod)
                if isinstance(result, Extension):
                    extensions.append(result)

    logger.info("加载了 {} 个扩展 (搜索路径: {})", len(extensions), search_paths)
    return extensions
