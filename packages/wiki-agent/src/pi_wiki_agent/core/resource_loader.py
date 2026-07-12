"""Resource loader for wiki-agent — discovers extensions, skills, and context files.

Mirrors pi_coding_agent.core.resource_loader with wiki-specific scoping.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from pi_coding_agent.core.diagnostics import ResourceDiagnostic


_CONTEXT_CANDIDATES = ["AGENTS.md", "CLAUDE.md"]


def _load_context_file_from_dir(dir_path: str) -> dict[str, str] | None:
    for filename in _CONTEXT_CANDIDATES:
        fpath = os.path.join(dir_path, filename)
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    return {"path": fpath, "content": f.read()}
            except OSError as e:
                print(f"Warning: Could not read {fpath}: {e}")
    return None


def _load_project_context_files(cwd: str | None = None, agent_dir: str | None = None) -> list[dict[str, str]]:
    from pi_coding_agent.config import get_agent_dir

    resolved_cwd = cwd or os.getcwd()
    resolved_agent_dir = agent_dir or get_agent_dir()

    context_files: list[dict[str, str]] = []
    seen: set[str] = set()

    global_ctx = _load_context_file_from_dir(resolved_agent_dir)
    if global_ctx:
        context_files.append(global_ctx)
        seen.add(global_ctx["path"])

    ancestor_files: list[dict[str, str]] = []
    current = resolved_cwd
    root = os.path.abspath("/")

    while True:
        ctx = _load_context_file_from_dir(current)
        if ctx and ctx["path"] not in seen:
            ancestor_files.insert(0, ctx)
            seen.add(ctx["path"])

        if os.path.abspath(current) == root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    context_files.extend(ancestor_files)
    return context_files


@dataclass
class ResourceLoaderOptions:
    cwd: str | None = None
    agent_dir: str | None = None
    settings_manager: Any = None
    additional_extension_paths: list[str] = field(default_factory=list)
    additional_skill_paths: list[str] = field(default_factory=list)
    no_extensions: bool = False
    no_skills: bool = False
    skills_override: Callable | None = None


class ResourceLoader:
    """Loads and manages wiki-agent resources (extensions, skills, context files).

    Mirrors the coding-agent DefaultResourceLoader with wiki-specific scoping:
    only extensions and skills are loaded (no themes, no prompt templates).
    """

    def __init__(self, options: ResourceLoaderOptions | None = None) -> None:
        from pi_coding_agent.config import CONFIG_DIR_NAME, get_agent_dir

        opts = options or ResourceLoaderOptions()
        self._cwd = opts.cwd or os.getcwd()
        self._agent_dir = opts.agent_dir or get_agent_dir()
        self._config_dir_name = CONFIG_DIR_NAME
        self._settings_manager = opts.settings_manager
        self._additional_extension_paths = list(opts.additional_extension_paths)
        self._additional_skill_paths = list(opts.additional_skill_paths)
        self._no_extensions = opts.no_extensions
        self._no_skills = opts.no_skills
        self._skills_override = opts.skills_override

        self._extensions_result: dict[str, Any] = {"extensions": [], "diagnostics": []}
        self._skills: list[Any] = []
        self._skill_diagnostics: list[ResourceDiagnostic] = []
        self._agents_files: list[dict[str, str]] = []
        self._last_skill_paths: list[str] = []
        self._last_extension_paths: list[str] = []

    # ── Public getters ────────────────────────────────────────────────────────

    def get_extensions(self) -> dict[str, Any]:
        return dict(self._extensions_result)

    def get_skills(self) -> dict[str, Any]:
        return {"skills": self._skills, "diagnostics": self._skill_diagnostics}

    def get_agents_files(self) -> dict[str, Any]:
        return {"agentsFiles": self._agents_files, "agents_files": self._agents_files}

    # ── Reload ────────────────────────────────────────────────────────────────

    async def reload(self) -> None:
        """Reload all resources from disk."""
        # Load extensions
        if not self._no_extensions:
            await self._load_extensions()

        # Load skills
        skill_paths = self._resolve_resource_paths_from_settings("skills") + self._additional_skill_paths
        merged_skill_paths = self._merge_paths([], skill_paths)
        self._last_skill_paths = merged_skill_paths
        self._update_skills_from_paths(merged_skill_paths)

        # Load AGENTS.md / CLAUDE.md context files
        self._agents_files = _load_project_context_files(self._cwd, self._agent_dir)

    # ── Extension loading ─────────────────────────────────────────────────────

    async def _load_extensions(self) -> None:
        ext_paths = self._resolve_resource_paths_from_settings("extensions") + self._additional_extension_paths

        if not ext_paths:
            self._extensions_result = {"extensions": [], "diagnostics": []}
        else:
            try:
                from pi_coding_agent.core.extensions.loader import load_extensions
                from pi_coding_agent.core.event_bus import create_event_bus
                event_bus = create_event_bus()
                base_result = await load_extensions(ext_paths, self._cwd, event_bus)
                self._extensions_result = {
                    "extensions": base_result.extensions,
                    "diagnostics": base_result.errors,
                }
            except Exception as e:
                self._extensions_result = {"extensions": [], "diagnostics": [{"type": "error", "message": str(e)}]}

    # ── Skills ────────────────────────────────────────────────────────────────

    def _update_skills_from_paths(self, skill_paths: list[str]) -> None:
        from .skills import LoadSkillsOptions, load_skills

        if self._no_skills and not skill_paths:
            skills_result = {"skills": [], "diagnostics": []}
        else:
            result = load_skills(
                LoadSkillsOptions(
                    cwd=self._cwd,
                    agent_dir=self._agent_dir,
                    skill_paths=skill_paths,
                    include_defaults=not self._no_skills,
                )
            )
            skills_result = {"skills": result.skills, "diagnostics": result.diagnostics}

        resolved = (
            self._skills_override(skills_result)
            if self._skills_override
            else skills_result
        )
        self._skills = resolved["skills"]
        self._skill_diagnostics = resolved.get("diagnostics", [])

    # ── Path helpers ──────────────────────────────────────────────────────────

    def _resolve_resource_paths_from_settings(self, resource_type: str) -> list[str]:
        if not self._settings_manager:
            return []
        try:
            getter = getattr(self._settings_manager, f"get_{resource_type}", None)
            if callable(getter):
                val = getter()
                if isinstance(val, list):
                    return [str(p) for p in val if isinstance(p, str)]
        except Exception:
            pass
        return []

    def _merge_paths(self, primary: list[str], additional: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for p in primary + additional:
            resolved = self._resolve_resource_path(p)
            if resolved not in seen:
                seen.add(resolved)
                merged.append(resolved)
        return merged

    def _resolve_resource_path(self, p: str) -> str:
        home = os.path.expanduser("~")
        t = p.strip()
        if t == "~":
            expanded = home
        elif t.startswith("~/"):
            expanded = os.path.join(home, t[2:])
        elif t.startswith("~"):
            expanded = os.path.join(home, t[1:])
        else:
            expanded = t
        return os.path.abspath(os.path.join(self._cwd, expanded))
