"""Model resolution for wiki-agent — mirrors pi_coding_agent/core/model_resolver.py"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .defaults import DEFAULT_THINKING_LEVEL

if TYPE_CHECKING:
    from .model_registry import ModelRegistry

DEFAULT_MODEL_PER_PROVIDER: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "anthropic": "claude-opus-4-7",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "openrouter": "deepseek/deepseek-chat",
}

_VALID_THINKING_LEVELS = {"minimal", "low", "medium", "high", "xhigh", "off"}


def is_valid_thinking_level(level: str) -> bool:
    return level in _VALID_THINKING_LEVELS


def resolve_default_model(registry: ModelRegistry, provider: str | None = None) -> object | None:
    """Resolve a default model for the given provider."""
    if provider:
        model_id = DEFAULT_MODEL_PER_PROVIDER.get(provider)
        if model_id:
            m = registry.find(provider, model_id)
            if m:
                return m
    for prov, mid in DEFAULT_MODEL_PER_PROVIDER.items():
        m = registry.find(prov, mid)
        if m and registry.get_api_key(prov):
            return m
    return None
