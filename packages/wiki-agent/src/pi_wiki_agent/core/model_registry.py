"""Model registry for wiki-agent — mirrors pi_coding_agent/core/model_registry.py"""

from __future__ import annotations

import json
import os
from typing import Any

from pi_coding_agent.core.model_registry import ModelRegistry as _BaseModelRegistry


class ModelRegistry(_BaseModelRegistry):
    """Wiki-aware model registry that wraps the coding-agent registry.

    Adds wiki-specific model defaults and custom model config from ~/.pi/agent/models.json.
    """

    def __init__(self, auth_storage: Any = None, models_json_path: str | None = None) -> None:
        super().__init__(auth_storage=auth_storage, models_json_path=models_json_path)

    @classmethod
    def create(cls, models_path: str | None = None) -> ModelRegistry:
        return cls(models_json_path=models_path)

    def get_wiki_models(self) -> list[dict]:
        """Return simplified model summaries for wiki use."""
        result: list[dict] = []
        for m in self.get_all():
            result.append({
                "name": getattr(m, "name", m.id),
                "provider": m.provider,
                "model_id": m.id,
                "api": m.api,
                "base_url": getattr(m, "base_url", ""),
                "context_window": m.context_window,
                "max_tokens": m.max_tokens,
                "reasoning": m.reasoning,
            })
        return result
