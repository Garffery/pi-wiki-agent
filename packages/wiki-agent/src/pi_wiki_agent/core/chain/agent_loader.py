"""Agent definition loader — discovers and parses .md agent definition files.

Mirrors pi-subagents' agent discovery and AgentConfig loading.
Agent definitions are markdown files with YAML frontmatter.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...logging import logger

# ── Discovery paths (priority: builtin < user < project) ─────────────────────

_BUILTIN_AGENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agents")
_USER_AGENTS_DIR = os.path.join(os.path.expanduser("~"), ".pi", "wiki-agent", "agents")


@dataclass
class AgentDefinition:
    """A loaded agent definition from a .md file.

    Mirrors AgentConfig in pi-subagents.
    """
    name: str
    description: str = ""
    system_prompt: str = ""          # The markdown body (role instructions)
    tools: list[str] | None = None   # e.g. ["read", "write", "edit"]
    model: str | None = None         # "provider:model_id"
    thinking: str | None = None      # "off"|"low"|"medium"|"high"
    output: str | None = None        # Default output file
    reads: list[str] | None = None   # Default files to read
    source_path: str = ""            # File this was loaded from
    raw_config: dict[str, Any] = field(default_factory=dict)


# ── YAML frontmatter parser (no heavy dependency) ────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns (config_dict, body_text).
    Uses a lightweight inline parser to avoid tomli/pyyaml dependency.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, content

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:]).strip()

    config: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] = []

    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Simple key: value
        if ":" in stripped:
            # Flush pending list
            if current_key and current_list:
                config[current_key] = current_list
                current_list = []

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # Scalar value
                config[key] = _parse_yaml_value(value)
                current_key = None
            else:
                # Start of a list
                current_key = key
                current_list = []
        elif stripped.startswith("- ") and current_key:
            item = stripped[2:].strip()
            item = item.strip('"').strip("'")
            current_list.append(item)

    # Flush last list
    if current_key and current_list:
        config[current_key] = current_list

    return config, body


def _parse_yaml_value(value: str) -> Any:
    """Parse a YAML scalar value."""
    value = value.strip()
    # Remove surrounding quotes
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    # Booleans
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    # Numbers
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ── Discovery ────────────────────────────────────────────────────────────────

def discover_agents(
    project_path: str | None = None,
    extra_paths: list[str] | None = None,
) -> list[AgentDefinition]:
    """Discover all agent definitions from configured paths.

    Priority (low to high):
      1. Builtin: <package>/agents/
      2. User:    ~/.pi/wiki-agent/agents/
      3. Project: <project>/.pi/agents/
      4. Extra:   extra_paths
    """
    search_dirs: list[tuple[str, str]] = []  # (path, source_label)

    # 1. Builtin
    if os.path.isdir(_BUILTIN_AGENTS_DIR):
        search_dirs.append((_BUILTIN_AGENTS_DIR, "builtin"))

    # 2. User
    if os.path.isdir(_USER_AGENTS_DIR):
        search_dirs.append((_USER_AGENTS_DIR, "user"))

    # 3. Project
    if project_path:
        project_agents = os.path.join(project_path, ".pi", "agents")
        if os.path.isdir(project_agents):
            search_dirs.append((project_agents, "project"))

    # 4. Extra
    if extra_paths:
        for p in extra_paths:
            if os.path.isdir(p):
                search_dirs.append((p, "extra"))

    # Load with override: higher priority overwrites lower
    agents_by_name: dict[str, AgentDefinition] = {}

    for directory, source in search_dirs:
        for md_file in sorted(Path(directory).glob("*.md")):
            try:
                agent = _load_agent_file(str(md_file))
                if agent:
                    agents_by_name[agent.name] = agent
            except Exception as e:
                logger.warning("加载 agent 定义失败: {} err={}", md_file, e)

    logger.info("发现 {} 个 agent 定义 (搜索路径: {})", len(agents_by_name), [d for d, _ in search_dirs])
    return list(agents_by_name.values())


def find_agent(name: str, project_path: str | None = None) -> AgentDefinition | None:
    """Find a single agent by name."""
    agents = discover_agents(project_path=project_path)
    for a in agents:
        if a.name == name:
            return a
    return None


def _load_agent_file(filepath: str) -> AgentDefinition | None:
    """Load and parse a single agent .md file."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    config, body = _parse_frontmatter(content)
    name = config.get("name")
    if not name:
        # Fallback: use filename without extension
        name = Path(filepath).stem

    return AgentDefinition(
        name=name,
        description=config.get("description", ""),
        system_prompt=body,
        tools=config.get("tools"),
        model=config.get("model"),
        thinking=config.get("thinking"),
        output=config.get("output"),
        reads=config.get("reads"),
        source_path=filepath,
        raw_config=config,
    )
