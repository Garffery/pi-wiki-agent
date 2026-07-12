"""SDK — public factory functions for creating wiki sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pi_ai.types import Model

from .settings_manager import SettingsManager
from .session_manager import SessionManager


@dataclass
class CreateWikiSessionOptions:
    cwd: str | None = None
    model: Model | None = None
    session_manager: SessionManager | None = None
    settings_manager: SettingsManager | None = None
    extra_tools: list[Any] = field(default_factory=list)
    auth_storage: Any = None
    model_registry: Any = None


@dataclass
class CreateWikiSessionResult:
    session: Any  # WikiSession
    extensions_result: Any = None
    model_fallback_message: str | None = None


async def create_wiki_session(options: CreateWikiSessionOptions | None = None) -> CreateWikiSessionResult:
    """Create a WikiSession with full extension loading and model resolution.

    This is the public entry point for creating wiki sessions programmatically.
    """
    from ..session import WikiSession

    if options is None:
        options = CreateWikiSessionOptions()

    kwargs: dict[str, Any] = {}
    if options.session_manager:
        kwargs["session_manager"] = options.session_manager
    if options.model:
        kwargs["model"] = options.model
    if options.settings_manager:
        kwargs["settings_manager"] = options.settings_manager
    if options.extra_tools:
        kwargs["extra_tools"] = options.extra_tools
    if options.auth_storage:
        kwargs["auth_storage"] = options.auth_storage
    if options.model_registry:
        kwargs["model_registry"] = options.model_registry

    session = WikiSession(options.cwd or ".", **kwargs)
    return CreateWikiSessionResult(session=session)


def create_wiki_session_sync(cwd: str | None = None, model: Model | None = None) -> Any:
    """Synchronous factory for WikiSession (for use in sync contexts)."""
    from .agent_session import WikiSession
    kwargs: dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    return WikiSession(cwd or ".", **kwargs)
