"""WikiModelRegistry — extends ModelRegistry with persistent CRUD for models.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pi_coding_agent.core.model_registry import ModelRegistry


class WikiModelRegistry(ModelRegistry):
    """Extends ModelRegistry with persistent add/remove for ~/.pi/agent/models.json."""

    MODEL_JSON = os.path.join(os.path.expanduser("~"), ".pi", "agent", "models.json")

    async def get_available_summaries(self) -> list[dict]:
        """Return simplified model list for frontend dropdown.

        Includes both built-in models with auth and custom models from models.json.
        """
        available = await self.get_available()

        result: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for m in available:
            key = (m.provider, m.id)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "name": getattr(m, "name", m.id) or m.id,
                "provider": m.provider,
                "model_id": m.id,
                "base_url": getattr(m, "base_url", "") or "",
                "api": m.api,
                "reasoning": m.reasoning,
                "context_window": m.context_window,
                "max_tokens": m.max_tokens,
            })
        return result

    def add_custom_model(
        self,
        name: str,
        provider: str,
        model_id: str,
        base_url: str,
        api_key: str = "",
    ) -> None:
        """Persist a new model to ~/.pi/agent/models.json and re-register it."""
        config = self._read_config()

        providers = config.setdefault("providers", {})
        prov_cfg = providers.setdefault(provider, {})
        prov_cfg.setdefault("baseUrl", base_url)
        if api_key:
            prov_cfg["apiKey"] = api_key

        models: list = prov_cfg.setdefault("models", [])
        # Remove existing entry with same id
        models[:] = [m for m in models if m.get("id") != model_id]
        models.append({
            "id": model_id,
            "name": name,
            "api": "openai-completions",
            "contextWindow": 65536,
            "maxTokens": 8192,
            "compat": {"supportsDeveloperRole": provider != "anthropic"},
        })

        self._write_config(config)

        # Register the new provider config in-memory
        self.register_provider(provider, prov_cfg)
        self.refresh()

    def remove_custom_model(self, provider: str, model_id: str) -> bool:
        """Remove a model from ~/.pi/agent/models.json."""
        config = self._read_config()
        providers = config.get("providers", {})
        prov_cfg = providers.get(provider, {})
        models: list = prov_cfg.get("models", [])
        original_len = len(models)
        models[:] = [m for m in models if m.get("id") != model_id]

        if len(models) == original_len:
            return False  # not found

        # Clean up empty provider
        if not models and not prov_cfg.get("modelOverrides"):
            providers.pop(provider, None)

        self._write_config(config)
        self.refresh()
        return True

    @staticmethod
    def _read_config() -> dict:
        path = WikiModelRegistry.MODEL_JSON
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def _write_config(config: dict) -> None:
        path = WikiModelRegistry.MODEL_JSON
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
