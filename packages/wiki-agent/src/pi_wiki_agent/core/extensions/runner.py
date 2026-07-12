"""Extension runner — dispatches events to extension handlers."""

from __future__ import annotations

from typing import Any

from .types import Extension, ExtensionContext


class ExtensionRunner:
    """Runs extensions and dispatches events to registered handlers.

    Pure extension dispatch — no built-in wiki guards (those live in wiki_tool_wrapper.py).
    """

    def __init__(self, extensions: list[Extension], cwd: str = "", session_id: str = "") -> None:
        self._extensions = extensions
        self._cwd = cwd
        self._session_id = session_id
        self._session_data: dict[str, Any] = {}

    @property
    def extensions(self) -> list[Extension]:
        return self._extensions

    def has_handlers(self, event_type: str) -> bool:
        return any(event_type in ext.handlers and len(ext.handlers[event_type]) > 0 for ext in self._extensions)

    def set_session_data(self, data: dict[str, Any]) -> None:
        """Set session-scoped data for extension handlers."""
        self._session_data = data

    def create_context(self) -> ExtensionContext:
        return ExtensionContext(cwd=self._cwd, session_id=self._session_id, session_data=self._session_data)

    async def emit(self, event: dict[str, Any]) -> Any | None:
        event_type = event.get("type", "")
        result = None
        for ext in self._extensions:
            for handler in ext.handlers.get(event_type, []):
                ctx = self.create_context()
                try:
                    r = await handler(ctx, event)
                    if r is not None:
                        result = r
                except Exception:
                    pass
        return result

    async def emit_tool_call(self, event) -> Any | None:
        """Dispatch a tool_call event to all extension handlers."""
        return await self.emit({"type": "tool_call", **event.__dict__})

    async def emit_tool_result(self, event) -> Any | None:
        return await self.emit({"type": "tool_result", **event.__dict__})

    async def emit_context(self, messages: list) -> list:
        result = await self.emit({"type": "context", "messages": messages})
        return result.get("messages", messages) if result else messages
