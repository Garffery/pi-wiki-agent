"""Session factory helpers — shared WikiSession creation logic.

Extracted from routes.py to be used by all endpoint modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request
from loguru import logger
from pi_wiki_agent import WikiSession
from pi_wiki_agent.core.settings_manager import Settings

if TYPE_CHECKING:
    from pi_wiki_desktop.wiki_model_registry import WikiModelRegistry


@dataclass
class WikiSessionOptions:
    """Options for creating a WikiSession.

    Mirrors CreateAgentSessionOptions in pi_coding_agent.core.sdk.
    """
    project_path: str
    settings: Settings | None = None

    @staticmethod
    def from_model_str(project_path: str, model_str: str | None = None) -> WikiSessionOptions:
        """Parse a model string 'provider:model_id' into Settings."""
        settings = None
        if model_str and ":" in model_str:
            provider, model_id = model_str.split(":", 1)
            settings = Settings(model_id=model_id, provider=provider)
        return WikiSessionOptions(project_path=project_path, settings=settings)


def get_or_create_session(
    options: WikiSessionOptions,
    registry: WikiModelRegistry,
) -> WikiSession:
    """Create a WikiSession from options.

    Model resolution is delegated to WikiSession via Settings.
    """
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")

    from pi_wiki_desktop.resources import get_resource_store
    store = get_resource_store()

    return WikiSession(
        options.project_path,
        model=None,
        settings=options.settings,
        model_registry=registry,
        extra_tools=store.get("extension_tools", []),
        extension_runner=store.get("extension_runner"),
        skills=store.get("skills", []),
        context_files=store.get("agents_files", []),
    )


def make_chain_session_factory(registry: WikiModelRegistry, default_model: str | None = None):
    """Create a session factory that injects shared resources into chain steps.

    Captures the same model_registry + resources used by the single-agent path,
    so chain steps get proper API key resolution and extension tools.
    Also forwards per-step agent events to the progress callback.
    """
    from pi_wiki_desktop.resources import get_resource_store
    store = get_resource_store()

    def factory(project_path, system_prompt=None, model=None, thinking=None, active_tools=None, **kwargs):
        from pi_wiki_agent import WikiSession as WS
        from pi_wiki_agent.core.settings_manager import Settings

        effective_model = model or default_model
        settings = Settings()
        if effective_model and ":" in effective_model:
            provider, model_id = effective_model.split(":", 1)
            settings.model_id = model_id
            settings.provider = provider
        if thinking:
            settings.thinking_level = thinking

        ws = WS(
            project_root=project_path,
            settings=settings,
            system_prompt=system_prompt,
            model_registry=registry,
            extra_tools=store.get("extension_tools", []),
            extension_runner=store.get("extension_runner"),
            skills=store.get("skills", []),
            context_files=store.get("agents_files", []),
            active_tools=active_tools,
        )

        event_callback = kwargs.get("event_callback")
        step_index = kwargs.get("step_index", 0)
        if event_callback:
            def _forward_agent_event(event):
                evt: dict = {}
                try:
                    if event.type == "message_update":
                        ae = getattr(event, "assistant_message_event", None)
                        if ae and hasattr(ae, "delta"):
                            evt = {"text": ae.delta}
                    elif event.type == "tool_execution_start":
                        evt = {"tool": getattr(event, "tool_name", ""),
                               "args": str(getattr(event, "args", ""))[:120]}
                    elif event.type == "tool_execution_end":
                        evt = {"tool": getattr(event, "tool_name", ""),
                               "is_error": getattr(event, "is_error", False)}
                    elif event.type == "message_start":
                        msg = getattr(event, "message", None)
                        if msg and hasattr(msg, "role"):
                            evt = {"role": msg.role}
                    else:
                        return
                    evt["type"] = event.type
                    evt["_chain_step"] = step_index
                    event_callback(step_index, "", "agent_event", evt)
                except Exception:
                    pass

            ws.subscribe(_forward_agent_event)

        return ws

    return factory


def get_model_registry(request: Request) -> WikiModelRegistry:
    """FastAPI dependency: extract WikiModelRegistry from app.state."""
    return request.app.state.model_registry
