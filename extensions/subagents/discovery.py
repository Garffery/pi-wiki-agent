"""
discovery.py — Agent file discovery, frontmatter parsing, and config merging.

Scans:
  ~/.pi/agent/agents/*.md   (user agents)
  <project>/.pi/agents/*.md (project agents)

Parses YAML frontmatter, produces AgentConfig objects.
Merges with per-field precedence: default < user < project.
"""
from __future__ import annotations

import os
from typing import Any

from .types import AgentConfig, ThinkingLevel


# ═══════════════════════════════════════════════════════════════════════════════
# Built-in default agents (mirrors TS default-agents.ts)
# ═══════════════════════════════════════════════════════════════════════════════

READ_ONLY_TOOLS = ["read", "bash", "grep", "find"]

DEFAULT_AGENTS: dict[str, AgentConfig] = {
    "general-purpose": AgentConfig(
        name="general-purpose",
        display_name="Agent",
        description="General-purpose agent for complex, multi-step tasks",
        system_prompt="",
        is_default=True,
    ),
    "Explore": AgentConfig(
        name="Explore",
        display_name="Explore",
        description="Fast codebase exploration agent (read-only)",
        registered_tools=READ_ONLY_TOOLS,
        system_prompt="""# CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS
You are a file search specialist. You excel at thoroughly navigating and exploring codebases.
Your role is EXCLUSIVELY to search and analyze existing code. You do NOT have access to file editing tools.

You are STRICTLY PROHIBITED from:
- Creating new files
- Modifying existing files
- Deleting files
- Moving or copying files
- Creating temporary files anywhere, including /tmp
- Using redirect operators (>, >>, |) or heredocs to write to files
- Running ANY commands that change system state

Use Bash ONLY for read-only operations: ls, git status, git log, git diff, find, cat, head, tail.

# Tool Usage
- Use the find tool for file pattern matching (NOT the bash find command)
- Use the grep tool for content search (NOT bash grep/rg command)
- Use the read tool for reading files (NOT bash cat/head/tail)
- Use Bash ONLY for read-only operations
- Make independent tool calls in parallel for efficiency
- Adapt search approach based on thoroughness level specified

# Output
- Use absolute file paths in all references
- Report findings as regular messages
- Do not use emojis
- Be thorough and precise""",
        is_default=True,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Frontmatter parsing
# ═══════════════════════════════════════════════════════════════════════════════

def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Naive YAML frontmatter splitter.

    Handles triple-dash delimited frontmatter blocks with flat key:value pairs
    and YAML array syntax (lines starting with "- ").
    Returns (frontmatter_dict, body_string).
    """
    if not content:
        return {}, ""

    if not content.startswith("---\n") and not content.startswith("---\r\n"):
        return {}, content

    # Find closing ---
    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return {}, content

    fm_raw = content[4:end_idx]
    body = content[end_idx + 5:].strip()

    frontmatter: dict[str, Any] = {}
    current_key: str | None = None
    current_values: list[str] | None = None

    for line in fm_raw.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue

        # Array item (continuation of previous key)
        if trimmed.startswith("- "):
            if current_key is not None:
                if current_values is None:
                    current_values = []
                current_values.append(trimmed[2:].strip())
            continue

        # Flush previous array before processing a new key
        if current_key is not None and current_values is not None:
            frontmatter[current_key] = current_values
            current_values = None

        colon_idx = trimmed.find(":")
        if colon_idx == -1:
            current_key = trimmed
            continue

        current_key = trimmed[:colon_idx].strip()
        raw_value = trimmed[colon_idx + 1:].strip()

        if not raw_value:
            current_values = []
            continue

        # Strip surrounding quotes
        frontmatter[current_key] = raw_value.strip("'\"").strip("'\"")
        current_values = None

    # Flush trailing array items
    if current_key is not None and current_values is not None:
        frontmatter[current_key] = current_values

    return frontmatter, body


# ═══════════════════════════════════════════════════════════════════════════════
# Frontmatter value helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _split_comma_list(value: str) -> list[str]:
    """Split comma-separated string, trim whitespace, strip brackets."""
    return [
        s.strip().strip("[]").strip()
        for s in value.split(",")
        if s.strip()
    ]


def _parse_string(fm: dict[str, Any], key: str) -> str | None:
    v = fm.get(key)
    return v if isinstance(v, str) and len(v) > 0 else None


def _parse_string_array(fm: dict[str, Any], key: str) -> list[str] | None:
    v = fm.get(key)
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and len(v) > 0:
        return _split_comma_list(v)
    return None


def _parse_bool(fm: dict[str, Any], key: str) -> bool | None:
    v = fm.get(key)
    if v is True or v == "true":
        return True
    if v is False or v == "false":
        return False
    return None


def _parse_number(fm: dict[str, Any], key: str) -> int | None:
    v = fm.get(key)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and len(v) > 0:
        try:
            return int(v)
        except (ValueError, TypeError):
            pass
    return None


def _parse_extensions(raw: Any) -> bool | list[str] | None:
    """Parse extensions/skills field from frontmatter."""
    if raw is False or raw == "false" or raw == "none":
        return False
    if raw is True or raw == "true" or raw == "all":
        return True
    if isinstance(raw, str) and len(raw) > 0:
        return _split_comma_list(raw)
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return None


def _parse_preload_skills(raw: Any) -> list[str] | None:
    """Parse preload_skills field. Does NOT accept true/'true'/'all'."""
    if raw is False or raw == "false" or raw == "none":
        return None
    if isinstance(raw, str) and len(raw) > 0:
        return _split_comma_list(raw)
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return None


def _parse_thinking_level(raw: str | None) -> ThinkingLevel | None:
    """Parse a thinking level string, returning a valid ThinkingLevel or None."""
    if not raw:
        return None
    valid: set[ThinkingLevel] = {"off", "minimal", "low", "medium", "high", "xhigh"}
    r = raw.strip().lower()
    if r in valid:
        return r  # type: ignore[return-value]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent file parsing
# ═══════════════════════════════════════════════════════════════════════════════

def parse_agent_file(
    content: str,
    source: str = "user",
) -> AgentConfig:
    """Parse a single agent .md file into an AgentConfig."""
    frontmatter, body = parse_frontmatter(content)

    name = _parse_string(frontmatter, "name") or "unknown"
    thinking_raw = _parse_string(frontmatter, "thinking")
    thinking_level = _parse_thinking_level(thinking_raw)

    return AgentConfig(
        name=name,
        display_name=_parse_string(frontmatter, "display_name") or "",
        description=_parse_string(frontmatter, "description") or "",
        tools=_parse_string_array(frontmatter, "tools"),
        exclude_tools=_parse_string_array(frontmatter, "exclude_tools"),
        extensions=_parse_extensions(frontmatter.get("extensions")),
        exclude_extensions=_parse_string_array(frontmatter, "exclude_extensions"),
        skills=_parse_extensions(frontmatter.get("skills")),
        preload_skills=_parse_preload_skills(frontmatter.get("preload_skills")),
        model=_parse_string(frontmatter, "model"),
        thinking_level=thinking_level,
        max_turns=_parse_number(frontmatter, "max_turns"),
        max_tokens=_parse_number(frontmatter, "max_tokens"),
        hidden=_parse_bool(frontmatter, "hidden"),
        system_prompt=body,
        registered_tools=_parse_string_array(frontmatter, "tools"),
        source="project" if source == "project" else "global",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Directory scanning
# ═══════════════════════════════════════════════════════════════════════════════

def scan_agent_files_in_dir(
    dir_path: str,
    source: str = "user",
) -> list[AgentConfig]:
    """
    Scan a directory for .md files and parse them into AgentConfig list.
    Returns empty list if directory doesn't exist.
    """
    if not os.path.isdir(dir_path):
        return []

    agents: list[AgentConfig] = []
    try:
        for entry in os.listdir(dir_path):
            if not entry.endswith(".md"):
                continue
            file_path = os.path.join(dir_path, entry)
            if not os.path.isfile(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                info = parse_agent_file(content, source)
                if info.name and info.name != "unknown":
                    agents.append(info)
            except OSError:
                pass
    except OSError:
        pass

    return agents


# ═══════════════════════════════════════════════════════════════════════════════
# Agent merging
# ═══════════════════════════════════════════════════════════════════════════════

def merge_agents(
    defaults: dict[str, AgentConfig],
    user_agents: list[AgentConfig],
    project_agents: list[AgentConfig],
) -> dict[str, AgentConfig]:
    """
    Merge default agents with user and project overrides.

    Per-field merge precedence (highest to lowest):
      1. project agents
      2. user agents
      3. default agents
    """
    result: dict[str, AgentConfig] = {}

    # Start with defaults (shallow copy)
    for name, config in defaults.items():
        result[name] = AgentConfig(
            name=config.name,
            display_name=config.display_name,
            description=config.description,
            system_prompt=config.system_prompt,
            model=config.model,
            thinking_level=config.thinking_level,
            max_turns=config.max_turns,
            max_tokens=config.max_tokens,
            tools=config.tools,
            exclude_tools=config.exclude_tools,
            registered_tools=config.registered_tools,
            extensions=config.extensions,
            exclude_extensions=config.exclude_extensions,
            skills=config.skills,
            preload_skills=config.preload_skills,
            is_default=config.is_default,
            hidden=config.hidden,
            source=config.source,
        )

    # Apply user overrides (middle priority), then project (highest priority)
    _merge_agent_overrides(result, user_agents)
    _merge_agent_overrides(result, project_agents)

    return result


def _merge_agent_overrides(
    result: dict[str, AgentConfig],
    agents: list[AgentConfig],
) -> None:
    """Apply a list of agent configs onto the result map, per-field merge."""
    for md in agents:
        if not md.name:
            continue
        existing = result.get(md.name)
        if existing:
            # Merge: md fields override existing where non-None/non-empty
            _apply_override(existing, md)
        else:
            result[md.name] = md


def _apply_override(target: AgentConfig, override: AgentConfig) -> None:
    """Merge override into target, per-field: non-None/non-empty wins."""
    if override.display_name:
        target.display_name = override.display_name
    if override.description:
        target.description = override.description
    if override.system_prompt:
        target.system_prompt = override.system_prompt
    if override.model is not None:
        target.model = override.model
    if override.thinking_level is not None:
        target.thinking_level = override.thinking_level
    if override.max_turns is not None:
        target.max_turns = override.max_turns
    if override.max_tokens is not None:
        target.max_tokens = override.max_tokens
    if override.tools is not None:
        target.tools = override.tools
    if override.exclude_tools is not None:
        target.exclude_tools = override.exclude_tools
    if override.registered_tools is not None:
        target.registered_tools = override.registered_tools
    if override.extensions is not None:
        target.extensions = override.extensions
    if override.exclude_extensions is not None:
        target.exclude_extensions = override.exclude_extensions
    if override.skills is not None:
        target.skills = override.skills
    if override.preload_skills is not None:
        target.preload_skills = override.preload_skills
    if override.hidden:
        target.hidden = override.hidden
    if override.source is not None:
        target.source = override.source
