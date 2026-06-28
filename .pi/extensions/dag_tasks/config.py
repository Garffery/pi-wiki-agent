"""
Configuration management for DAG Tasks
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .types import DagTasksConfig


def config_path(cwd: str) -> str:
    """Get the config file path."""
    return os.path.join(cwd, ".pi", "dag-tasks", "dag-tasks-config.json")


def load_config(cwd: str) -> DagTasksConfig:
    """Load configuration from file."""
    try:
        with open(config_path(cwd), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return DagTasksConfig(**data)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return DagTasksConfig()


def save_config(config: DagTasksConfig, cwd: str) -> None:
    """Save configuration to file."""
    file_path = config_path(cwd)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(vars(config), f, indent=2)
