"""Extension discovery and loading — mirrors pi_coding_agent/core/extensions/loader.py

Discovers and loads extensions from:
1. Global: ~/.pi/wiki-agent/extensions/
2. Local:  <cwd>/.pi/extensions/
3. Explicit paths from settings / additional_extension_paths
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...logging import logger
from .types import Extension, ToolDefinition

# ── Default search paths ──────────────────────────────────────────────────────

_GLOBAL_EXT_DIR = os.path.join(os.path.expanduser("~"), ".pi", "wiki-agent", "extensions")
_LOCAL_EXT_DIR_NAME = os.path.join(".pi", "extensions")


# ── Manifest reader ────────────────────────────────────────────────────────────

def read_pi_manifest(directory: str) -> dict[str, Any] | None:
    """Read pi manifest from pyproject.toml [tool.pi] or package.json "pi"."""
    pyproject = os.path.join(directory, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                pass
            else:
                return _read_toml_manifest(pyproject, tomllib)
        else:
            return _read_toml_manifest(pyproject, tomllib)

    pkg_json = os.path.join(directory, "package.json")
    if os.path.exists(pkg_json):
        import json
        try:
            with open(pkg_json, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("pi")
        except Exception:
            pass

    return None


def _read_toml_manifest(path: str, tomllib: Any) -> dict[str, Any] | None:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return data.get("tool", {}).get("pi", {})
    except Exception:
        return None


# ── Directory scanner ──────────────────────────────────────────────────────────

def discover_extensions_in_dir(directory: str) -> list[str]:
    """Discover extension paths in a directory.

    Handles three cases:
    - .py files (not starting with _)
    - Subdirectories with __init__.py (package extensions)
    - Subdirectories with pyproject.toml or package.json manifest
    """
    if not os.path.isdir(directory):
        return []

    paths: list[str] = []
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        if os.path.isfile(full) and entry.endswith(".py") and not entry.startswith("_"):
            paths.append(full)
        elif os.path.isdir(full):
            index = os.path.join(full, "__init__.py")
            if os.path.exists(index):
                paths.append(full)
            else:
                manifest = read_pi_manifest(full)
                if manifest and manifest.get("extensions"):
                    for ext_path in manifest["extensions"]:
                        resolved = os.path.join(full, ext_path)
                        if os.path.exists(resolved):
                            paths.append(resolved)

    return paths


# ── Module loading ─────────────────────────────────────────────────────────────

def _load_py_module(path: str) -> Any | None:
    """Load a Python module from a .py file or package directory."""
    try:
        if os.path.isdir(path):
            module_name = f"wiki_ext_{abs(hash(path))}"
            spec = importlib.util.spec_from_file_location(
                module_name,
                os.path.join(path, "__init__.py"),
                submodule_search_locations=[path],
            )
        else:
            module_name = f"wiki_ext_{abs(hash(path))}"
            spec = importlib.util.spec_from_file_location(module_name, path)

        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
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
                import asyncio
                import inspect
                ret = fn(api)
                if inspect.isawaitable(ret):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.run_until_complete(ret)
                    except RuntimeError:
                        asyncio.run(ret)
            except Exception:
                pass
            return ext
    return None


# ── Extension API ──────────────────────────────────────────────────────────────

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


# ── Public API ─────────────────────────────────────────────────────────────────

@dataclass
class LoadExtensionsResult:
    extensions: list[Extension] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def discover_extensions(extra_paths: list[str] | None = None, cwd: str | None = None) -> LoadExtensionsResult:
    """Discover and load all extensions from configured paths.

    Mirrors coding-agent's discover_and_load_extensions():
    1. Global: ~/.pi/wiki-agent/extensions/
    2. Local:  <cwd>/.pi/extensions/
    3. Explicit: extra_paths from settings / additional_extension_paths
    """
    all_paths: list[str] = []

    # 1. Global extensions
    all_paths.extend(discover_extensions_in_dir(_GLOBAL_EXT_DIR))

    # 2. Local project extensions
    resolved_cwd = cwd or os.getcwd()
    local_dir = os.path.join(resolved_cwd, _LOCAL_EXT_DIR_NAME)
    all_paths.extend(discover_extensions_in_dir(local_dir))

    # 3. Explicit paths
    if extra_paths:
        for p in extra_paths:
            resolved = os.path.abspath(p) if not os.path.isabs(p) else p
            if os.path.exists(resolved):
                all_paths.append(resolved)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in all_paths:
        rp = os.path.abspath(p)
        if rp not in seen:
            seen.add(rp)
            unique.append(p)

    # Load all discovered paths
    result = LoadExtensionsResult()
    for path in unique:
        mod = _load_py_module(path)
        if mod is None:
            result.errors.append({"path": path, "error": "无法加载模块"})
            continue
        ext = _invoke_factory(mod)
        if ext is not None:
            result.extensions.append(ext)
        else:
            result.errors.append({"path": path, "error": "未找到 extension_factory / activate / default 导出"})

    logger.info(
        "加载了 {} 个扩展 (错误: {}, 搜索路径: global={}, local={}, extra={})",
        len(result.extensions), len(result.errors),
        _GLOBAL_EXT_DIR, local_dir, extra_paths or [],
    )
    return result
