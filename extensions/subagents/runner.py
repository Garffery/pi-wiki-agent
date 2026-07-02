"""
runner.py — Sub-agent execution engine.

Creates pi_agent.Agent instances, configures them for sub-agent tasks,
runs the agent loop, and collects results.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from pi_agent import Agent, AgentOptions
from pi_agent.agent_loop import agent_loop
from pi_agent.types import (
    AgentContext,
    AgentLoopConfig,
    AgentTool,
    ThinkingLevel,
)
from pi_ai.types import Message, Model, TextContent, UserMessage

from .types import (
    AgentConfig,
    AgentRecord,
    LifetimeUsage,
    add_usage,
)


def _build_tools(cwd: str, tool_names: list[str]) -> list[AgentTool]:
    """Build agent tools from the coding-agent tool factories."""
    tools: list[AgentTool] = []
    try:
        from pi_coding_agent.core.tools.bash import create_bash_tool
        from pi_coding_agent.core.tools.edit import create_edit_tool
        from pi_coding_agent.core.tools.find import create_find_tool
        from pi_coding_agent.core.tools.grep import create_grep_tool
        from pi_coding_agent.core.tools.read import create_read_tool
        from pi_coding_agent.core.tools.write import create_write_tool

        factory_map: dict[str, Any] = {
            "bash": create_bash_tool,
            "edit": create_edit_tool,
            "find": create_find_tool,
            "grep": create_grep_tool,
            "read": create_read_tool,
            "write": create_write_tool,
        }

        for name in tool_names:
            factory = factory_map.get(name)
            if factory:
                try:
                    tool = factory(cwd)
                    tools.append(tool)
                except Exception:
                    pass
    except ImportError:
        pass

    return tools


def _build_system_prompt(
    agent_config: AgentConfig | None,
    cwd: str,
) -> str:
    """Build the system prompt for a sub-agent."""
    if agent_config and agent_config.system_prompt:
        return agent_config.system_prompt

    # Minimal default system prompt
    return f"""You are a coding sub-agent working in {cwd}.
Complete the assigned task thoroughly and return your results.
You have access to file tools (read, write, edit, bash, grep, find) to complete your work."""


async def run_subagent(
    agent_config: AgentConfig | None,
    prompt: str,
    model: Model,
    tools: list[AgentTool],
    thinking_level: ThinkingLevel = "off",
    max_turns: int | None = None,
    cwd: str | None = None,
    record: AgentRecord | None = None,
) -> str:
    """
    Run a sub-agent session and return the response text.

    Args:
        agent_config: Agent type configuration
        prompt: The task prompt to send to the sub-agent
        model: The resolved model to use
        tools: Filtered list of tools available to the sub-agent
        thinking_level: Thinking level for the sub-agent
        max_turns: Maximum number of turns (None = unlimited)
        cwd: Working directory for the sub-agent
        record: Optional AgentRecord for stats tracking

    Returns:
        The final response text from the sub-agent
    """
    effective_cwd = cwd or os.getcwd()

    # Validate model
    if model is None or not getattr(model, "provider", "") or not getattr(model, "id", ""):
        raise ValueError(
            "No valid model configured for sub-agent. "
            "Set a default model in settings or provide an API key."
        )

    system_prompt = _build_system_prompt(agent_config, effective_cwd)

    # Build context
    context = AgentContext(
        system_prompt=system_prompt,
        messages=[],
        tools=tools,
    )

    # Build config with API key resolution
    def _resolve_api_key(provider: str) -> str | None:
        """Resolve API key for a provider from AuthStorage or env."""
        try:
            from pi_coding_agent.core.auth_storage import AuthStorage
            key = AuthStorage().get_api_key(provider)
            if key:
                return key
        except Exception:
            pass
        from pi_ai.env_api_keys import get_env_api_key
        return get_env_api_key(provider)

    config = AgentLoopConfig(
        model=model,
        convert_to_llm=_default_convert_to_llm,
        get_api_key=_resolve_api_key,
    )

    # Stream events to accumulate response
    response_text = ""
    turn_count = 0

    ev_stream = agent_loop(
        prompts=[UserMessage(role="user", content=prompt, timestamp=0)],
        context=context,
        config=config,
    )

    async for event in ev_stream:
        event_type = event.type if hasattr(event, "type") else event.get("type", "") if isinstance(event, dict) else ""
        if event_type == "message_update":
            ame = event.assistant_message_event if hasattr(event, "assistant_message_event") else event.get("assistant_message_event") if isinstance(event, dict) else None
            if ame:
                ame_type = ame.type if hasattr(ame, "type") else ame.get("type", "") if isinstance(ame, dict) else ""
                ame_delta = ame.delta if hasattr(ame, "delta") else ame.get("delta", "") if isinstance(ame, dict) else ""
                if ame_type == "text_delta":
                    response_text += ame_delta

        elif event_type == "message_end":
            msg = event.message if hasattr(event, "message") else event.get("message") if isinstance(event, dict) else None
            if msg:
                msg_role = msg.role if hasattr(msg, "role") else msg.get("role", "") if isinstance(msg, dict) else ""
                if msg_role == "assistant":
                    if record:
                        usage = _extract_usage(msg)
                        if usage:
                            add_usage(record.stats.lifetime_usage, usage)

        elif event_type == "tool_end":
            if record:
                record.stats.tool_uses += 1

        elif event_type == "turn_end":
            turn_count += 1
            if record:
                record.stats.turn_count = turn_count

            if max_turns and turn_count >= max_turns:
                break

        elif event_type == "agent_end":
            break

    # If no streaming text captured, extract from last assistant message
    ev_result = await ev_stream.result()
    if not response_text.strip() and ev_result:
        response_text = _extract_last_assistant_text(ev_result)

    return response_text.strip()


def _default_convert_to_llm(messages: list[Any]) -> list[Message]:
    """Default converter: keep only LLM-compatible messages."""
    result: list[Message] = []
    for m in messages:
        if hasattr(m, "role") and getattr(m, "role") in ("user", "assistant", "toolResult"):
            result.append(m)
    return result


def _extract_usage(msg: Any) -> LifetimeUsage | None:
    """Extract LifetimeUsage from an assistant message's usage field."""
    usage = getattr(msg, "usage", None)
    if not usage:
        return None
    try:
        cost_total = 0.0
        cost = getattr(usage, "cost", None)
        if cost and hasattr(cost, "total"):
            cost_total = float(getattr(cost, "total", 0))

        return LifetimeUsage(
            input=int(getattr(usage, "input", 0) or 0),
            output=int(getattr(usage, "output", 0) or 0),
            cache_write=int(getattr(usage, "cacheWrite", 0) or 0),
            cost=cost_total,
        )
    except (TypeError, ValueError):
        return None


def _get_field(obj: Any, field: str, default: Any = None) -> Any:
    """Get a field from a dict or object, returning default if missing."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _extract_last_assistant_text(messages: list[Any]) -> str:
    """Get the last assistant text from message history."""
    for msg in reversed(messages):
        if _get_field(msg, "role") != "assistant":
            continue
        content = _get_field(msg, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            texts = []
            for item in content:
                if _get_field(item, "type") == "text":
                    texts.append(_get_field(item, "text", ""))
            result = "".join(texts).strip()
            if result:
                return result
    return ""
