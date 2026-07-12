"""FilterManager — load, apply, and manage commit filters."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from ..logging import logger
from .types import FilterConfig, FilterRule

CONFIG_FILE = "filter.json"
BUILTIN_RULES: list[FilterRule] = [
    FilterRule(type="path", pattern=".wiki/**", description="忽略 .wiki 目录下的变更（默认）"),
]


class FilterManager:
    """Manages per-project commit filters for wiki sync.

    Filters are stored in .wiki/filter.json under the project root.
    Two rule types:

    - **path** — glob patterns matching file paths. A file matching ANY path
      rule is excluded. Supports `*`, `**`, `?`, `[seq]`.
    - **message** — regex patterns matching commit messages. If the message
      matches ANY message rule, the entire commit is skipped.

    Usage::

        fm = FilterManager("/path/to/project")
        # Check if a commit should be skipped
        if fm.should_skip("fix typo", ["src/main.py", ".wiki/Home.md"]):
            return  # nothing to do
        # Filter out excluded files, keep only relevant ones
        relevant = fm.filter_files(["src/main.py", ".wiki/Home.md"])
        # → ["src/main.py"]
    """

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._wiki_root = self._project_root / ".wiki"
        self._config_path = self._wiki_root / CONFIG_FILE

    @property
    def config(self) -> FilterConfig:
        """Load current filter configuration."""
        if not self._config_path.exists():
            cfg = FilterConfig(rules=list(BUILTIN_RULES))
            self._save(cfg)
            return cfg
        try:
            data = json.loads(self._config_path.read_text("utf-8"))
            return FilterConfig(**data)
        except (json.JSONDecodeError, TypeError):
            return FilterConfig(rules=list(BUILTIN_RULES))

    def _save(self, cfg: FilterConfig) -> None:
        self._wiki_root.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            cfg.model_dump_json(indent=2, exclude_defaults=False), "utf-8"
        )

    # ── Public API ──────────────────────────────────────────────────────

    def should_skip_commit(self, changed_files: list[str], message: str = "") -> bool:
        """Return True if the entire commit should be skipped.

        A commit is skipped if:
        - The message matches any message-type rule.
        - After filtering paths, no relevant files remain.
        """
        cfg = self.config
        if not cfg.enabled:
            return False

        # Message rules — any match → skip entire commit
        for rule in cfg.rules:
            if rule.type == "message":
                try:
                    if re.search(rule.pattern, message):
                        logger.info("提交被 message 规则跳过: pattern={}", rule.pattern)
                        return True
                except re.error:
                    continue

        return False

    def filter_files(self, changed_files: list[str]) -> list[str]:
        """Return files that pass all path filters (i.e., files to keep).

        Files matching any path-type rule are excluded.
        """
        cfg = self.config
        if not cfg.enabled:
            return list(changed_files)

        result: list[str] = []
        for f in changed_files:
            excluded = False
            for rule in cfg.rules:
                if rule.type == "path":
                    if fnmatch.fnmatch(f, rule.pattern):
                        excluded = True
                        break
            if not excluded:
                result.append(f)
        logger.debug("filter_files: {} 个输入 → {} 个通过 (过滤了 {} 个)", len(changed_files), len(result), len(changed_files) - len(result))
        return result

    def add_rule(self, rule: FilterRule) -> None:
        """Add a filter rule and persist."""
        cfg = self.config
        cfg.rules.append(rule)
        self._save(cfg)

    def remove_rule(self, index: int) -> bool:
        """Remove a rule by index. Returns False if index is out of range."""
        cfg = self.config
        if index < 0 or index >= len(cfg.rules):
            return False
        cfg.rules.pop(index)
        self._save(cfg)
        return True

    def get_rules(self) -> list[FilterRule]:
        """Get all current rules (built-in + custom)."""
        return list(self.config.rules)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all filters."""
        cfg = self.config
        cfg.enabled = enabled
        self._save(cfg)
