"""Session pool — manages AgentSession lifecycle and wires events to WebSocket."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pi_coding_agent.core.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.core.agent_session import AgentSession
from pi_agent.types import AgentEvent

from .serialization import serialize_agent_event

logger = logging.getLogger(__name__)


class SessionPool:
    """Manages a pool of AgentSession instances with WebSocket event forwarding."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()
        self._ws_manager: Any = None  # Set after WebSocket manager is created

    def set_ws_manager(self, ws_manager: Any) -> None:
        self._ws_manager = ws_manager

    async def create_session(self, cwd: str | None = None) -> dict[str, Any]:
        """Create a new agent session and return info."""
        import os

        result = await create_agent_session(
            CreateAgentSessionOptions(cwd=cwd or os.getcwd())
        )
        session = result.session

        async with self._lock:
            self._sessions[session.session_id] = session

        self._wire_events(session)
        return self._session_info(session)

    async def get_session(self, session_id: str) -> AgentSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._lock:
            active = {s.session_id: self._session_info(s) for s in self._sessions.values()}

        # Also scan disk for historical sessions not currently in memory
        from pi_coding_agent.core.session_manager import SessionManager
        import json as _json
        import os as _os

        def _read_model_from_file(file_path: str) -> str:
            """Extract the last-used model from a session file."""
            try:
                entries: list[dict] = []
                with open(file_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = _json.loads(line)
                            if obj.get("type") != "session":
                                entries.append(obj)
                        except _json.JSONDecodeError:
                            pass
                for entry in reversed(entries):
                    etype = entry.get("type")
                    if etype == "model_change":
                        provider = entry.get("provider", "")
                        model_id = entry.get("modelId", "")
                        if provider and model_id:
                            return f"{provider}/{model_id}"
                        return model_id or ""
                    if etype == "message":
                        msg = entry.get("message", {})
                        if isinstance(msg, dict) and msg.get("role") == "assistant":
                            model = msg.get("model", "")
                            if model:
                                return model
            except Exception:
                pass
            return ""

        disk_sessions = await SessionManager.list_all()
        for info in disk_sessions:
            sid = info.session_id
            if sid not in active:
                cwd = info.cwd_path or ""
                model_name = _read_model_from_file(info.file_path)
                active[sid] = {
                    "session_id": sid,
                    "cwd": cwd,
                    "model": model_name or None,
                    "message_count": info.entry_count,
                    "is_streaming": False,
                    "updated_at": info.updated_at,
                    "label": info.label,
                    "entry_count": info.entry_count,
                }
            else:
                if not active[sid].get("updated_at"):
                    active[sid]["updated_at"] = info.updated_at
                if not active[sid].get("label"):
                    active[sid]["label"] = info.label
                if not active[sid].get("entry_count"):
                    active[sid]["entry_count"] = info.entry_count

        result = list(active.values())
        result.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
        return result

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.dispose()
                return True

        # Try to delete on-disk session file
        from pi_coding_agent.core.session_manager import SessionManager
        import asyncio as _asyncio
        import os as _os

        def _find_and_delete() -> bool:
            sessions_dir = _os.path.join(_os.path.expanduser("~"), ".pi", "agent", "sessions")
            if not _os.path.isdir(sessions_dir):
                return False
            for root, _dirs, files in _os.walk(sessions_dir):
                for fname in files:
                    if fname == f"{session_id}.jsonl":
                        file_path = _os.path.join(root, fname)
                        _os.remove(file_path)
                        return True
            return False

        return await _asyncio.to_thread(_find_and_delete)

    async def send_prompt(
        self, session_id: str, message: str, images: list[Any] | None = None
    ) -> dict[str, Any]:
        """Send a prompt to a session. Returns immediately; events stream via WS."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.is_streaming:
            session.follow_up(message)
            return {"status": "queued", "session_id": session_id}

        asyncio.create_task(self._run_prompt(session, message, images))
        return {"status": "started", "session_id": session_id}

    async def abort_session(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        await session.abort()
        return {"status": "aborted", "session_id": session_id}

    async def compact_session(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        summary = await session.compact()
        return {"status": "compacted", "session_id": session_id, "summary": summary}

    async def get_session_info(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        return self._session_info(session)

    async def get_session_stats(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        return session.get_session_stats()

    async def get_context_usage(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        return session.get_context_usage()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        messages = session.state.messages if hasattr(session, "state") else []
        result = []
        for msg in messages:
            try:
                result.append(msg.model_dump(mode="json"))
            except Exception:
                result.append({"role": getattr(msg, "role", "unknown"), "content": str(msg)})
        return result

    async def get_tools(self, session_id: str) -> list[str] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        return session.get_active_tool_names()

    async def set_model(self, session_id: str, provider: str, model_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        from pi_ai import get_model
        model = get_model(provider, model_id)
        await session.set_model(model)
        return {"status": "ok", "model": f"{provider}/{model_id}"}

    async def cycle_model(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        result = await session.cycle_model()
        if result:
            return {"status": "ok", "model": result}
        return {"status": "no_change"}

    async def set_thinking_level(self, session_id: str, level: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session.set_thinking_level(level)
        return {"status": "ok", "thinking_level": level}

    async def cycle_thinking_level(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        result = session.cycle_thinking_level()
        return {"status": "ok", "thinking_level": result}

    async def fork_session(self, session_id: str, entry_id: str | None = None) -> dict[str, Any]:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        forked = await session.fork(entry_id)
        async with self._lock:
            self._sessions[forked.session_id] = forked
        self._wire_events(forked)
        return self._session_info(forked)

    async def get_session_tree(self, session_id: str) -> list[dict[str, Any]] | None:
        session = await self.get_session(session_id)
        if not session:
            return None

        def serialize_node(node) -> dict[str, Any]:
            entry = node.entry
            return {
                "entry": {
                    "id": entry.id,
                    "type": entry.type,
                    "timestamp": entry.timestamp,
                    "parent_id": entry.parent_id,
                    "data": {
                        "role": entry.data.get("message", {}).get("role", "")
                        if isinstance(entry.data.get("message"), dict)
                        else ""
                    } if entry.type == "message" else {},
                },
                "label": node.label,
                "children": [serialize_node(c) for c in node.children],
            }

        tree = session.session_manager.get_tree()
        return [serialize_node(n) for n in tree]

    async def get_fork_points(self, session_id: str) -> list[dict[str, str]] | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        return session.getUserMessagesForForking() if hasattr(session, "getUserMessagesForForking") else []

    # ── private helpers ──────────────────────────────────────────────────────

    async def _run_prompt(self, session: AgentSession, message: str, images: list[Any] | None) -> None:
        try:
            await session.prompt(message, images=images)
        except Exception as e:
            logger.error(f"Prompt error for session {session.session_id}: {e}")
            if self._ws_manager:
                await self._ws_manager.broadcast(
                    session.session_id,
                    {"type": "error", "message": str(e)},
                )

    def _wire_events(self, session: AgentSession) -> None:
        def on_event(event: AgentEvent) -> None:
            serialized = serialize_agent_event(event)
            if self._ws_manager:
                asyncio.create_task(
                    self._ws_manager.broadcast(session.session_id, serialized)
                )

        session.subscribe(on_event)

    def _session_info(self, session: AgentSession) -> dict[str, Any]:
        info = session.get_session_info()
        info["is_streaming"] = session.is_streaming
        return info
