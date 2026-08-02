"""
In-memory subagent runner for workflow orchestration.

Mirrors src/agent.ts from pi-dynamic-workflows.
Each agent() call spawns a fresh AgentSession that runs in a temp session directory.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from pi_ai.types import AssistantMessage, TextContent
from pi_coding_agent.core.agent_session import AgentSession
from pi_coding_agent.core.auth_storage import AuthStorage
from pi_coding_agent.core.model_registry import ModelRegistry
from pi_coding_agent.core.session_manager import SessionManager
from pi_coding_agent.core.settings_manager import Settings
from .structured_output import StructuredOutputCapture, create_structured_output_tool


class WorkflowAgent:
    """Creates and runs in-memory subagent sessions."""

    def __init__(
        self,
        *,
        cwd: str,
        model: Any = None,
        model_registry: ModelRegistry | None = None,
        auth_storage: AuthStorage | None = None,
        extra_tools: list | None = None,
    ):
        self.cwd = cwd
        self.model = model
        self.model_registry = model_registry or ModelRegistry()
        self.auth_storage = auth_storage or AuthStorage()
        self.extra_tools = extra_tools or []
        self.last_session_path: str | None = None

    async def run(
        self,
        prompt: str,
        *,
        label: str | None = None,
        schema: dict | None = None,
        instructions: str | None = None,
        signal: asyncio.Event | None = None,
        event_callback: Any = None,
        active_tools: list[str] | None = None,
        system_prompt: str | None = None,
        skill_names: list[str] | None = None,
        resume_from: str | None = None,
    ) -> Any:
        """
        Run a subagent with the given prompt.

        Args:
            prompt: The task for the subagent.
            label: Short label for logging.
            schema: Optional JSON Schema for structured output.
            instructions: Extra system guidance.
            signal: Abort signal.
            event_callback: Optional callback(evt_dict) for agent internal events.
            active_tools: Optional tool name whitelist (None = all 7 built-in tools).
            system_prompt: Optional role-specific system prompt override.
            skill_names: Optional skill names to load and inject into system prompt.
            resume_from: Optional path to an existing JSONL session file to resume.

        Returns:
            Subagent's final text output, or validated object if schema is provided.
        """
        # ── Build full prompt ──
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if instructions:
            parts.append(instructions)
        parts.append(f"Task: {prompt}")
        if label:
            parts.insert(0, f"Task label: {label}")

        enrich_parts: list[str] = []
        if schema:
            enrich_parts.extend([
                "Final output contract:",
                "- Your final action MUST be a structured_output tool call.",
                "- The structured_output arguments are the return value of this subagent.",
                "- Do not emit a prose final answer instead of structured_output.",
                "- If you need to inspect files or run commands first, do so, then call structured_output exactly once.",
            ])

        full_prompt = "\n\n".join([p for p in parts if p] + enrich_parts)

        # ── Load and inject skills ──
        if skill_names:
            try:
                from pi_wiki_agent.core.skills import load_skills, format_skills_for_prompt
                all_skills = load_skills()
                skill_map = {s.name: s for s in all_skills.skills}
                skills = []
                for name in skill_names:
                    if name in skill_map:
                        skills.append(skill_map[name])
                if skills:
                    skill_text = format_skills_for_prompt(skills)
                    full_prompt = skill_text + "\n\n" + full_prompt
            except Exception:
                pass  # skill loading is best-effort

        # ── Build extra tools (structured output only; built-in tools are added by AgentSession) ──
        subagent_tools = list(self.extra_tools)

        # ── Structured output ──
        capture: StructuredOutputCapture | None = None
        if schema:
            capture = StructuredOutputCapture()
            subagent_tools.append(create_structured_output_tool(schema, capture))

        import logging
        _log = logging.getLogger("pi_wiki_agent")

        # ── Settings ──
        settings = Settings(
            thinking_level="off",
            model_id=self.model.id if self.model else None,
            provider=self.model.provider if self.model else None,
        )

        # ── Create session (resume or new) ──
        if resume_from and os.path.exists(resume_from):
            session = AgentSession(
                cwd=self.cwd,
                model=self.model,
                settings=settings,
                session_manager=SessionManager.open(resume_from),
                auth_storage=self.auth_storage,
                model_registry=self.model_registry,
                extra_tools=subagent_tools,
            )
            self.last_session_path = resume_from
        else:
            session = AgentSession(
                cwd=self.cwd,
                model=self.model,
                settings=settings,
                session_manager=SessionManager.in_memory(self.cwd),
                auth_storage=self.auth_storage,
                model_registry=self.model_registry,
                extra_tools=subagent_tools,
            )
            self.last_session_path = session._session_manager.get_session_file()

        # Ensure structured_output is active when schema is used
        if active_tools and capture:
            active_tools = list(active_tools) + ["structured_output"]

        # Apply tool whitelist if specified
        if active_tools:
            session.set_active_tools_by_name(active_tools)

        _log.info(
            "Subagent [%s] session: model=%s/%s, requested_tools=%s, active_tools=%s",
            label,
            self.model.provider if self.model else "?",
            self.model.id if self.model else "?",
            active_tools or "all",
            [t.name for t in session._agent.state.tools],
        )

        # ── Subscribe to agent events → forward to callback ──
        if event_callback:
            def _forward_event(event):
                try:
                    evt: dict = {}
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
                    else:
                        return
                    evt["type"] = event.type
                    evt["_subagent"] = label
                    event_callback(evt)
                except Exception:
                    pass

            session._agent.subscribe(_forward_event)

        # ── Wire abort ──
        abort_handler_installed = False

        async def _on_abort():
            await session.abort()

        try:
            if signal and signal.is_set():
                raise asyncio.CancelledError("Subagent was aborted")

            if signal:
                # Poll signal and abort session when set
                async def _watch_abort():
                    await signal.wait()
                    await session.abort()

                abort_task = asyncio.ensure_future(_watch_abort())
                abort_handler_installed = True

            _log.info(
                "Subagent [%s] sending prompt (%d chars). first=%s... last=%s...",
                label, len(full_prompt),
                full_prompt[:200].replace("\n", "\\n"),
                full_prompt[-200:].replace("\n", "\\n"),
            )
            sys_prompt = session._agent.state.system_prompt
            _log.info(
                "Subagent [%s] system_prompt (%d chars): %s...%s",
                label, len(sys_prompt or ""),
                (sys_prompt or "")[:200],
                (sys_prompt or "")[-200:],
            )
            await session.prompt(full_prompt)
            _log.info("Subagent [%s] prompt returned", label)

            if signal and signal.is_set():
                raise asyncio.CancelledError("Subagent was aborted")

            # ── Extract result ──
            if schema and capture and capture.called:
                return capture.value

            text = self._last_assistant_text(session)
            if not text:
                msgs = session._agent.state.messages
                _log.warning(
                    "Subagent [%s] returned empty text. capture_called=%s, total_messages=%d",
                    label, capture.called if capture else False, len(msgs),
                )
                for i, m in enumerate(msgs):
                    role = getattr(m, "role", "?")
                    content = getattr(m, "content", None)
                    stop = getattr(m, "stop_reason", None)
                    # preview content
                    content_preview = ""
                    if isinstance(content, list):
                        for c in content[:3]:
                            if hasattr(c, "type"):
                                if c.type == "text":
                                    content_preview += f"[text:{getattr(c,'text','')[:80]}] "
                                elif c.type == "tool_use":
                                    content_preview += f"[tool_use:{getattr(c,'name','')}] "
                                else:
                                    content_preview += f"[{c.type}] "
                            elif isinstance(c, dict):
                                content_preview += f"[dict:{c.get('type','')}] "
                    _log.warning(
                        "  msg[%d] role=%s stop=%s content=%s",
                        i, role, stop, content_preview or "(empty)",
                    )
            return text

        finally:
            if abort_handler_installed:
                abort_task.cancel()
                try:
                    await abort_task
                except (asyncio.CancelledError, Exception):
                    pass
            session.dispose()

    def _last_assistant_text(self, session: AgentSession) -> str:
        """Extract the last assistant text from session messages."""
        messages = session._agent.state.messages
        for msg in reversed(messages):
            role = getattr(msg, "role", "")
            if role != "assistant":
                continue
            content = getattr(msg, "content", [])
            if not isinstance(content, list):
                continue
            # content is a list of TextContent
            texts = []
            for part in content:
                if hasattr(part, "text"):
                    texts.append(part.text)
                elif isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part["text"])
            text = "".join(texts).strip()
            if text:
                return text
        return ""
