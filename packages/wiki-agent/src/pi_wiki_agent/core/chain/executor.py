"""Chain executor — serial agent orchestration with template handoff.

Mirrors executeChain() in pi-subagents:
  for each step:
    1. resolve template ({task}, {previous}, {outputs.name})
    2. create session via factory
    3. prompt → wait → collect result
    4. prev = result.output  (handoff to next step)
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable, Awaitable

from ...logging import logger
from .agent_loader import discover_agents, AgentDefinition
from .templates import build_step_prompt
from .types import ChainConfig, ChainResult, ChainStep, StepResult

# Session factory type: (project_path, system_prompt, model, thinking, active_tools) → session
SessionFactory = Callable[..., Any]
# Progress callback: (step_index, agent_name, event_type, data) → None
ProgressCallback = Callable[[int, str, str, dict[str, Any]], None] | None


async def execute_chain(
    config: ChainConfig,
    session_factory: SessionFactory | None = None,
    on_progress: ProgressCallback = None,
) -> ChainResult:
    """Execute a chain of agents sequentially.

    Each step runs in its own session. Output from step N is passed as
    {previous} to step N+1.

    Args:
        config: Chain configuration (steps, task, project_path).
        session_factory: Optional factory function to create sessions.
            Signature: (project_path, system_prompt, model, active_tools) -> session-like object.
            If None, uses the default _default_session_factory.

    Returns:
        ChainResult with per-step results and aggregated output.
    """
    factory = session_factory or _default_session_factory

    # Discover agents for this project
    agents = discover_agents(project_path=config.project_path)
    agent_map: dict[str, AgentDefinition] = {a.name: a for a in agents}

    # Create chain working directory
    chain_dir = config.chain_dir or tempfile.mkdtemp(prefix="wiki_chain_")
    logger.info("agent chain share workplace: {}", chain_dir)
    os.makedirs(chain_dir, exist_ok=True)

    step_results: list[StepResult] = []
    outputs: dict[str, str] = {}
    prev = ""

    for i, step in enumerate(config.steps):
        logger.info("Chain step {}/{}: agent={}", i + 1, len(config.steps), step.agent)

        # Notify progress: step starting
        if on_progress:
            on_progress(i, step.agent, "step_start", {"total": len(config.steps)})

        # ── Lookup agent definition ─────────────────────────────────────────
        agent_def = agent_map.get(step.agent)
        if agent_def is None:
            err_msg = f"未找到 agent 定义: {step.agent}"
            logger.error(err_msg)
            step_results.append(StepResult(
                agent=step.agent, step_index=i, exit_code=1,
                error=err_msg,
            ))
            return ChainResult(
                steps=step_results, success=False, error=err_msg,
                outputs=outputs,
            )

        # ── Resolve template ────────────────────────────────────────────────
        template = step.task or ("{task}" if i == 0 else "{previous}")
        logger.info("当前agent:{},当前的任务是:{}",step.agent, template)
        output_file = step.output or agent_def.output
        logger.info("当前agent输出文件路径:{}", output_file)
        reads = step.reads or agent_def.reads

        prompt_text = build_step_prompt(
            template=template,
            task=config.task,
            prev=prev,
            outputs=outputs,
            chain_dir=chain_dir,
            reads=reads,
            output_file=output_file,
            vars=config.vars,
        )

        logger.info("发送给agent的任务:{}", prompt_text)

        # ── Resolve model ───────────────────────────────────────────────────
        model_str = step.model or agent_def.model
        thinking = step.thinking or agent_def.thinking

        # ── Build system prompt ─────────────────────────────────────────────
        system_prompt = agent_def.system_prompt if agent_def.system_prompt else None

        logger.info("系统提示词:{}", system_prompt)

        # ── Resolve active tools ────────────────────────────────────────────
        active_tools = step.extra.get("active_tools") if step.extra else None
        if active_tools is None:
            active_tools = agent_def.tools

        # ── Execute step ────────────────────────────────────────────────────
        logger.info("on_process:{}",on_progress)
        try:
            session = factory(
                project_path=config.project_path,
                system_prompt=system_prompt,
                model=model_str,
                thinking=thinking,
                active_tools=active_tools,
                event_callback=on_progress,
                step_index=i,
            )
            await session.prompt(prompt_text)
            result_text = session.get_last_assistant_text()

            await _close_session(session)

            step_result = StepResult(
                agent=step.agent,
                step_index=i,
                output=result_text,
                exit_code=0,
                output_file=output_file,
            )
            if on_progress:
                on_progress(i, step.agent, "step_end", {"output": result_text[:500] if result_text else None})
        except Exception as e:
            logger.error("Chain step {} failed: {}", step.agent, e)
            step_result = StepResult(
                agent=step.agent,
                step_index=i,
                exit_code=1,
                error=str(e),
            )
            if on_progress:
                on_progress(i, step.agent, "step_error", {"error": str(e)})

        step_results.append(step_result)

        # ── Stop chain on error ─────────────────────────────────────────────
        if step_result.exit_code != 0:
            return ChainResult(
                steps=step_results,
                success=False,
                error=step_result.error,
                all_pages_modified=[],
                outputs=outputs,
            )

        # ── Handoff: update prev and named outputs ──────────────────────────
        if step_result.output:
            prev = step_result.output
        if step.as_ and step_result.output:
            outputs[step.as_] = step_result.output

    # ── Aggregate results ───────────────────────────────────────────────────
    all_modified: list[str] = []
    for sr in step_results:
        all_modified.extend(sr.pages_modified)

    return ChainResult(
        steps=step_results,
        success=True,
        all_pages_modified=all_modified,
        outputs=outputs,
    )


# ── Default session factory ───────────────────────────────────────────────────

def _default_session_factory(
    project_path: str,
    system_prompt: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    active_tools: list[str] | None = None,
    model_registry: Any = None,
    extra_tools: list[Any] | None = None,
    extension_runner: Any = None,
    skills: list[Any] | None = None,
    context_files: list[dict[str, str]] | None = None,
) -> Any:
    """Default factory: creates a WikiSession.

    Kept separate so callers can inject a custom factory without
    importing WikiSession directly (loose coupling).
    """
    from ..agent_session import WikiSession
    from ..settings_manager import Settings

    settings = Settings()
    if model and ":" in model:
        provider, model_id = model.split(":", 1)
        settings.model_id = model_id
        settings.provider = provider
    if thinking:
        settings.thinking_level = thinking

    ws = WikiSession(
        project_root=project_path,
        settings=settings,
        system_prompt=system_prompt,
        model_registry=model_registry,
        extra_tools=extra_tools,
        extension_runner=extension_runner,
        skills=skills,
        context_files=context_files,
        active_tools=active_tools,
    )
    return ws


async def _close_session(session: Any) -> None:
    """Close a session if it has a close method."""
    if hasattr(session, "close") and callable(session.close):
        try:
            await session.close()
        except Exception:
            pass
