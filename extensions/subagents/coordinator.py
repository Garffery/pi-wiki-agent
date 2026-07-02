"""
coordinator.py — Spawn-and-track coordination for subagents.

Single entry point for spawning sub-agents (foreground and background).
Owns: live status tracking, background agent tracking, nudge batch emission.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .manager import AgentManager
from .types import SHORT_ID_LENGTH, AgentRecord, get_status_note

# Batch delay for nudges (seconds)
NUDGE_DELAY = 0.2


class SpawnCoordinator:
    """Coordinates sub-agent spawn, tracking, and completion nudges."""

    def __init__(self, manager: AgentManager, api: Any = None) -> None:
        self._manager = manager
        self._api = api  # ExtensionAPI reference for send_message
        self._background_agent_ids: set[str] = set()
        self._live_status: dict[str, dict[str, Any]] = {}
        self._disposed = False

        # Nudge batching
        self._pending_nudges: set[str] = set()
        self._nudge_task: asyncio.Task[Any] | None = None

    # ── Spawn ─────────────────────────────────────────────────────────────

    async def spawn(
        self,
        type_name: str,
        prompt: str,
        description: str,
        model_key: str | None = None,
        max_turns: int | None = None,
        max_tokens: int | None = None,
        thinking_level: str | None = None,
        grace_turns: int = 6,
        worktree_path: str | None = None,
        worktree_label: str | None = None,
        invocation: dict[str, Any] | None = None,
        run_in_background: bool = False,
        runner_factory: Any = None,
    ) -> dict[str, Any]:
        """Spawn a sub-agent and return agent_id + record."""
        live_status: dict[str, Any] = {"active_tools": {}, "response_text": ""}
        self._live_status[type_name] = live_status

        agent_id = self._manager.spawn(
            type_name=type_name,
            prompt=prompt,
            description=description,
            model_key=model_key,
            max_turns=max_turns,
            max_tokens=max_tokens,
            worktree_path=worktree_path,
            worktree_label=worktree_label,
            invocation=invocation,
            is_background=run_in_background,
        )

        if run_in_background:
            self._background_agent_ids.add(agent_id)

        record = self._manager.get_record(agent_id)
        if not record:
            return {"agent_id": agent_id, "record": None}

        if runner_factory:
            runner_coro = runner_factory(record)
            self._manager.attach_runner(agent_id, runner_coro)

        if not run_in_background:
            if record.execution.promise:
                try:
                    await record.execution.promise
                except asyncio.CancelledError:
                    pass
            self._live_status.pop(agent_id, None)

        return {"agent_id": agent_id, "record": record}

    # ── Status ────────────────────────────────────────────────────────────

    def live_status(self, agent_id: str) -> dict[str, Any] | None:
        return self._live_status.get(agent_id)

    def is_background(self, agent_id: str) -> bool:
        return agent_id in self._background_agent_ids

    # ── Completion + Nudge ────────────────────────────────────────────────

    def on_agent_complete(self, record: AgentRecord) -> None:
        """Called by AgentManager when an agent completes."""
        is_bg = record.id in self._background_agent_ids

        if is_bg:
            self._schedule_nudge(record.id)

        self._background_agent_ids.discard(record.id)
        self._live_status.pop(record.id, None)

    def _schedule_nudge(self, agent_id: str) -> None:
        """Batch nudges within NUDGE_DELAY window to coalesce rapid completions."""
        self._pending_nudges.add(agent_id)
        if self._nudge_task is None or self._nudge_task.done():
            self._nudge_task = asyncio.ensure_future(self._emit_batch())

    async def _emit_batch(self) -> None:
        """Wait for batch window, then emit all pending nudges."""
        await asyncio.sleep(NUDGE_DELAY)
        batch = list(self._pending_nudges)
        self._pending_nudges.clear()

        for agent_id in batch:
            self._emit_nudge(agent_id)

    def _emit_nudge(self, agent_id: str) -> None:
        """Push a background agent's result back to the parent session."""
        if self._disposed:
            return

        api = self._api
        if api is None:
            return

        record = self._manager.get_record(agent_id)
        if not record:
            return

        from .tools import build_agent_details
        details = build_agent_details(record, include_stats=True, include_status=True)
        status_note = get_status_note(record.lifecycle.status)
        content = (
            f'[Subagent "{record.display.type}" {record.lifecycle.status}]\n\n'
            f"{record.result or ''}{status_note}"
        )

        # steer = inject before next LLM call, followUp = queue after idle
        deliver_as = "steer"  # Default: interrupt parent with result
        ok = api.send_message(
            content,
            custom_type="subagent-result",
            details=details,
            deliver_as=deliver_as,
            trigger_turn=True,
        )

        if not ok:
            # Fallback: send_message not wired yet — log it
            pass

    # ── Queries ───────────────────────────────────────────────────────────

    def get_running_agents(self) -> list[AgentRecord]:
        return [
            r for r in self._manager.list_agents()
            if r.lifecycle.status in ("running", "queued")
        ]

    # ── Cleanup ───────────────────────────────────────────────────────────

    def dispose(self) -> None:
        self._disposed = True
        if self._nudge_task and not self._nudge_task.done():
            self._nudge_task.cancel()
        self._pending_nudges.clear()
        self._background_agent_ids.clear()
        self._live_status.clear()
