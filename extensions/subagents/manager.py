"""
manager.py — Agent lifecycle tracking, per-model concurrency, and queuing.

Supports per-model and per-provider concurrency limits with queuing.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from .logging import AgentOutputLog
from .types import (
    AgentAccumulatedStats,
    AgentDisplayInfo,
    AgentExecutionState,
    AgentLifecycle,
    AgentRecord,
    AgentStatus,
    LifetimeUsage,
    add_usage,
    get_lifetime_total,
    is_terminal_status,
)

# ── Constants ─────────────────────────────────────────────────────────────────

AGENT_ID_PREFIX_LENGTH = 17
DEFAULT_CONCURRENCY_LIMIT = 4
CLEANUP_AGE_CUTOFF_SEC = 10 * 60  # 10 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrency slot
# ═══════════════════════════════════════════════════════════════════════════════

class ConcurrencySlot:
    """Per-model concurrency state."""
    def __init__(self, limit: int = DEFAULT_CONCURRENCY_LIMIT) -> None:
        self.limit = max(1, limit)
        self.running = 0


# ═══════════════════════════════════════════════════════════════════════════════
# AgentManager
# ═══════════════════════════════════════════════════════════════════════════════

OnAgentComplete = Callable[[AgentRecord], None]
OnAgentStart = Callable[[AgentRecord], None]


class AgentManager:
    """Tracks agents, per-model concurrency, background execution."""

    def __init__(
        self,
        on_complete: OnAgentComplete | None = None,
        concurrency_config: dict[str, Any] | None = None,
        on_start: OnAgentStart | None = None,
        buffer_size: int = 0,
    ) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._on_complete = on_complete
        self._on_start = on_start
        self._buffer_size = buffer_size
        self._total_agent_cost = 0.0

        # Concurrency
        cc = concurrency_config or {}
        self._default_concurrency = cc.get("default", DEFAULT_CONCURRENCY_LIMIT)
        self._concurrency_slots: dict[str, ConcurrencySlot] = {}
        self._provider_slots: dict[str, ConcurrencySlot] = {}

        for provider, limit in cc.get("providers", {}).items():
            self._provider_slots[provider] = ConcurrencySlot(limit)
        for model_key, limit in cc.get("models", {}).items():
            self._concurrency_slots[model_key] = ConcurrencySlot(limit)

        self._queue: list[dict[str, Any]] = []

    # ── Concurrency ───────────────────────────────────────────────────────

    def set_concurrency(self, config: dict[str, Any]) -> None:
        """Update concurrency configuration."""
        self._default_concurrency = config.get("default", DEFAULT_CONCURRENCY_LIMIT)
        for provider, limit in config.get("providers", {}).items():
            slot = self._provider_slots.get(provider)
            if slot:
                slot.limit = max(1, limit)
            else:
                self._provider_slots[provider] = ConcurrencySlot(limit)
        for model_key, limit in config.get("models", {}).items():
            slot = self._concurrency_slots.get(model_key)
            if slot:
                slot.limit = max(1, limit)
            else:
                self._concurrency_slots[model_key] = ConcurrencySlot(limit)
        self._drain_queue()

    def _get_slot(self, model_key: str) -> ConcurrencySlot:
        """Get or create a concurrency slot. Per-model > per-provider > default."""
        slot = self._concurrency_slots.get(model_key)
        if slot:
            return slot
        provider = model_key.split("/")[0]
        provider_slot = self._provider_slots.get(provider)
        if provider_slot:
            return provider_slot
        slot = ConcurrencySlot(self._default_concurrency)
        self._concurrency_slots[model_key] = slot
        return slot

    # ── Spawn ─────────────────────────────────────────────────────────────

    def spawn(
        self,
        type_name: str,
        prompt: str,
        description: str,
        model_key: str | None = None,
        max_turns: int | None = None,
        max_tokens: int | None = None,
        worktree_path: str | None = None,
        worktree_label: str | None = None,
        invocation: dict[str, Any] | None = None,
        is_background: bool = False,
    ) -> str:
        """Spawn an agent and return its ID immediately."""
        agent_id = uuid.uuid4().hex[:AGENT_ID_PREFIX_LENGTH]

        queued = False
        concurrency_slot: ConcurrencySlot | None = None
        if model_key:
            slot = self._get_slot(model_key)
            if slot.running >= slot.limit:
                queued = True
                self._queue.append({
                    "id": agent_id,
                    "model_key": model_key,
                    "type_name": type_name,
                    "prompt": prompt,
                    "description": description,
                    "max_turns": max_turns,
                    "max_tokens": max_tokens,
                    "worktree_path": worktree_path,
                    "worktree_label": worktree_label,
                    "invocation": invocation,
                    "is_background": is_background,
                })
            else:
                concurrency_slot = slot

        record = AgentRecord(
            id=agent_id,
            lifecycle=AgentLifecycle(
                status="queued" if queued else "running",
                started_at=time.time(),
            ),
            display=AgentDisplayInfo(
                type=type_name,
                description=description,
                invocation=invocation,
                worktree_path=worktree_path,
                worktree_label=worktree_label,
            ),
            execution=AgentExecutionState(
                abort_event=asyncio.Event(),
            ),
            stats=AgentAccumulatedStats(
                lifetime_usage=LifetimeUsage(),
                max_turns=max_turns,
            ),
        )
        self._agents[agent_id] = record

        if queued:
            return agent_id

        # Start agent
        self._start_agent(
            agent_id=agent_id,
            record=record,
            type_name=type_name,
            prompt=prompt,
            description=description,
            model_key=model_key,
            max_turns=max_turns,
            max_tokens=max_tokens,
            worktree_path=worktree_path,
            worktree_label=worktree_label,
            invocation=invocation,
            is_background=is_background,
            concurrency_slot=concurrency_slot,
        )
        return agent_id

    def _start_agent(
        self,
        agent_id: str,
        record: AgentRecord,
        type_name: str,
        prompt: str,
        description: str,
        model_key: str | None = None,
        max_turns: int | None = None,
        max_tokens: int | None = None,
        worktree_path: str | None = None,
        worktree_label: str | None = None,
        invocation: dict[str, Any] | None = None,
        is_background: bool = False,
        concurrency_slot: ConcurrencySlot | None = None,
    ) -> None:
        """Actually start an agent (called immediately or from queue drain)."""
        if concurrency_slot:
            concurrency_slot.running += 1

        record.lifecycle.status = "running"
        record.lifecycle.started_at = time.time()

        # Create output log
        output_log = AgentOutputLog(agent_id, prompt)
        record.execution.output_log = output_log
        record.display.output_file = output_log.path

        if self._on_start:
            self._on_start(record)

        # The actual runner is injected by the coordinator
        # We store the spawn args so runner.py can pick them up
        record.execution.abort_event = asyncio.Event()

    def attach_runner(
        self,
        agent_id: str,
        runner_coro: Any,  # coroutine
    ) -> None:
        """Attach an async runner coroutine to an agent record."""
        record = self._agents.get(agent_id)
        if not record:
            return

        async def _run() -> None:
            slot = self._get_slot(record.display.invocation.get("model_key", "") if record.display.invocation else "")
            try:
                result_text = await runner_coro
                if record.lifecycle.status not in ("stopped",):
                    record.lifecycle.status = "completed"
                record.result = result_text
            except asyncio.CancelledError:
                if record.lifecycle.status not in ("stopped",):
                    record.lifecycle.status = "aborted"
            except Exception as e:
                if record.lifecycle.status not in ("stopped",):
                    record.lifecycle.status = "error"
                record.error = str(e)
            finally:
                record.lifecycle.completed_at = time.time()
                if record.execution.output_log:
                    try:
                        record.execution.output_log.finalize(
                            turn_count=record.stats.turn_count,
                            tool_use_count=record.stats.tool_uses,
                            total_tokens=int(get_lifetime_total(record.stats.lifetime_usage)),
                            cost=record.stats.lifetime_usage.cost,
                        )
                    except Exception:
                        pass
                    record.execution.output_log = None

                if slot:
                    slot.running -= 1

                self._safe_notify_complete(record)
                self._drain_queue()

        record.execution.promise = asyncio.ensure_future(_run())

    # ── Queue draining ────────────────────────────────────────────────────

    def _drain_queue(self) -> None:
        """Start queued agents up to the per-model concurrency limits."""
        started: set[str] = set()
        for entry in self._queue:
            eid = entry["id"]
            record = self._agents.get(eid)
            if not record or record.lifecycle.status != "queued":
                continue
            slot = self._get_slot(entry["model_key"])
            if slot.running >= slot.limit:
                continue
            try:
                self._start_agent(
                    agent_id=eid,
                    record=record,
                    type_name=entry["type_name"],
                    prompt=entry["prompt"],
                    description=entry["description"],
                    model_key=entry.get("model_key"),
                    max_turns=entry.get("max_turns"),
                    max_tokens=entry.get("max_tokens"),
                    worktree_path=entry.get("worktree_path"),
                    worktree_label=entry.get("worktree_label"),
                    invocation=entry.get("invocation"),
                    is_background=entry.get("is_background", False),
                    concurrency_slot=slot,
                )
                started.add(eid)
            except Exception as e:
                record.lifecycle.status = "error"
                record.error = str(e)
                record.lifecycle.completed_at = time.time()
                started.add(eid)
                self._safe_notify_complete(record)
        self._queue = [e for e in self._queue if e["id"] not in started]

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _safe_notify_complete(self, record: AgentRecord) -> None:
        """Notify completion callback, ignoring errors."""
        self._total_agent_cost += record.stats.lifetime_usage.cost
        try:
            if self._on_complete:
                self._on_complete(record)
        except Exception:
            pass

    def set_on_complete(self, cb: OnAgentComplete) -> None:
        self._on_complete = cb

    def get_total_agent_cost(self) -> float:
        return self._total_agent_cost

    def get_record(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        return sorted(
            self._agents.values(),
            key=lambda r: r.lifecycle.started_at,
            reverse=True,
        )

    def abort(self, agent_id: str) -> bool:
        """Stop an agent by aborting its session or removing from queue."""
        record = self._agents.get(agent_id)
        if not record:
            return False
        return self._stop_agent(record)

    def _stop_agent(self, record: AgentRecord) -> bool:
        if record.lifecycle.status == "queued":
            self._queue = [e for e in self._queue if e["id"] != record.id]
        elif record.lifecycle.status != "running":
            return False
        else:
            if record.execution.abort_event:
                record.execution.abort_event.set()
            # Cancel the running task
            if record.execution.promise:
                record.execution.promise.cancel()
        record.lifecycle.status = "stopped"
        record.lifecycle.completed_at = time.time()
        return True

    def cleanup(self) -> None:
        """Evict old completed records."""
        cutoff = time.time() - CLEANUP_AGE_CUTOFF_SEC
        to_remove: list[str] = []
        for agent_id, record in self._agents.items():
            if not is_terminal_status(record.lifecycle.status):
                continue
            completed_at = record.lifecycle.completed_at or 0
            if completed_at >= cutoff:
                continue
            to_remove.append(agent_id)
        for agent_id in to_remove:
            del self._agents[agent_id]

    async def dispose(self) -> None:
        """Dispose all agents and clear state."""
        self._queue.clear()
        for record in self._agents.values():
            if record.execution.abort_event:
                record.execution.abort_event.set()
            if record.execution.promise and not record.execution.promise.done():
                record.execution.promise.cancel()
        self._agents.clear()
