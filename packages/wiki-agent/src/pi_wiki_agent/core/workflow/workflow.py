"""
Core workflow engine: script parsing, sandbox execution, agent orchestration.

Mirrors src/workflow.ts from pi-dynamic-workflows.
"""
from __future__ import annotations

import ast
import asyncio
import json as json_module
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from pi_wiki_agent.logging import logger


# ============================================================================
# Data types
# ============================================================================


@dataclass
class WorkflowMetaPhase:
    title: str
    detail: str | None = None
    model: str | None = None


@dataclass
class WorkflowMeta:
    name: str
    description: str
    when_to_use: str | None = None
    phases: list[WorkflowMetaPhase] | None = None


@dataclass
class AgentOptions:
    label: str | None = None
    phase: str | None = None
    schema: dict | None = None
    model: str | None = None
    isolation: str | None = None
    agent_type: str | None = None
    agent: str | None = None  # agent definition name → lookup in args['agent_defs']


@dataclass
class WorkflowRunResult:
    meta: WorkflowMeta
    result: Any
    logs: list[str]
    phases: list[str]
    agent_count: int
    duration_ms: float


@dataclass
class WorkflowRunOptions:
    args: Any = None
    agent: Any = None  # WorkflowAgent instance; when None, one is created from model/model_registry/auth_storage
    concurrency: int | None = None
    token_budget: int | None = None
    cwd: str | None = None
    signal: Any = None  # asyncio.Event for abort
    # Fields for creating a default WorkflowAgent when agent is not provided
    model: Any = None
    model_registry: Any = None
    auth_storage: Any = None
    # Progress callbacks
    on_agent_start: Any = None  # Callable[[dict], None] — fired when an agent begins
    on_agent_end: Any = None    # Callable[[dict], None] — fired when an agent finishes
    on_phase: Any = None        # Callable[[str], None]  — fired when phase() is called
    on_event: Any = None        # Callable[[dict], None] — fired for agent internal events (tool calls, text)


# ============================================================================
# AST literal evaluator for meta
# ============================================================================


def _evaluate_ast_node(node: ast.AST) -> Any:
    """Evaluate a literal AST node. Raises ValueError for non-literal nodes."""
    match node:
        case ast.Constant(value=v) if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        case ast.Constant(value=v):
            raise ValueError(f"unsupported constant type: {type(v).__name__}")
        case ast.List(elts=elts):
            return [_evaluate_ast_node(e) for e in elts]
        case ast.Dict(keys=keys, values=values):
            result: dict = {}
            for k, v in zip(keys, values):
                if k is None:
                    raise ValueError("dict unpacking (**) not allowed in meta")
                key = _evaluate_ast_node(k)
                if not isinstance(key, (str, int, float, bool)):
                    raise ValueError(f"dict key must be string or number, got {type(key).__name__}")
                result[key] = _evaluate_ast_node(v)
            return result
        case ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=(int() | float()) as v)):
            return -v
        case ast.Expr(value=inner):
            return _evaluate_ast_node(inner)
        case _:
            raise ValueError(f"non-literal node in meta: {type(node).__name__}")


# ============================================================================
# Deterministic check
# ============================================================================


class _DeterminismVisitor(ast.NodeVisitor):
    """Walk AST and reject dangerous constructs."""

    def visit_Import(self, node: ast.Import):
        raise ValueError("import statements are not allowed in workflow scripts")

    def visit_ImportFrom(self, node: ast.ImportFrom):
        raise ValueError("import statements are not allowed in workflow scripts")

    def visit_Call(self, node: ast.Call):
        # Reject open(), eval(), exec(), compile(), __import__(), globals(), locals()
        match node.func:
            case ast.Name(id=name) if name in ("open", "eval", "exec", "compile", "globals", "locals", "__import__"):
                raise ValueError(f"{name}() is not allowed in workflow scripts")
            case ast.Attribute(attr=attr) if attr in ("__import__", "__subclasses__", "__class__"):
                raise ValueError(f".{attr} is not allowed in workflow scripts")
        self.generic_visit(node)


# ============================================================================
# Script parser
# ============================================================================


def parse_workflow_script(script: str) -> tuple[WorkflowMeta, str]:
    """
    Parse a workflow script, extracting meta from the first statement.

    The first statement must be: meta = { name: '...', description: '...' }

    Returns (meta, body) where body is the script with the meta assignment removed.
    """
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as e:
        raise ValueError(f"workflow script has invalid syntax: {e}") from e

    if not tree.body:
        raise ValueError("workflow script is empty")

    first = tree.body[0]

    # First statement must be: meta = { ... }
    if not isinstance(first, ast.Assign):
        raise ValueError("`meta = { name, description }` must be the first statement in the script")
    if len(first.targets) != 1:
        raise ValueError("`meta = { name, description }` must be the first statement in the script")
    target = first.targets[0]
    if not isinstance(target, ast.Name) or target.id != "meta":
        raise ValueError("first assignment must be to `meta`")
    if first.value is None:
        raise ValueError("meta must have a literal value")

    try:
        meta_value = _evaluate_ast_node(first.value)
    except ValueError as e:
        raise ValueError(f"meta must be a plain literal object: {e}") from e

    if not isinstance(meta_value, dict):
        raise ValueError("meta must be a dict literal")

    meta = _validate_meta(meta_value)

    # Run determinism check on the body (everything after meta assignment)
    for node in tree.body[1:]:
        _DeterminismVisitor().visit(node)

    # Extract body text: everything after the meta = {...} statement
    # Use ast's end position info (Python 3.8+)
    meta_end_line = first.end_lineno
    script_lines = script.split("\n")
    body_lines = script_lines[meta_end_line:]  # end_lineno is 1-based, so this skips the meta line
    body = "\n".join(body_lines)

    return meta, body


def _validate_meta(value: dict) -> WorkflowMeta:
    name = value.get("name")
    description = value.get("description")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("meta.name must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("meta.description must be a non-empty string")

    when_to_use = value.get("whenToUse") or value.get("when_to_use")
    if when_to_use is not None and not isinstance(when_to_use, str):
        raise ValueError("meta.whenToUse must be a string")

    phases_raw = value.get("phases")
    phases: list[WorkflowMetaPhase] | None = None
    if phases_raw is not None:
        if not isinstance(phases_raw, list):
            raise ValueError("meta.phases must be a list")
        phases = []
        for p in phases_raw:
            if not isinstance(p, dict) or not isinstance(p.get("title"), str):
                raise ValueError("each meta phase must have a title string")
            phases.append(
                WorkflowMetaPhase(
                    title=p["title"],
                    detail=p.get("detail"),
                    model=p.get("model"),
                )
            )

    return WorkflowMeta(
        name=name.strip(),
        description=description.strip(),
        when_to_use=when_to_use if isinstance(when_to_use, str) else None,
        phases=phases,
    )


# ============================================================================
# Sandbox helpers
# ============================================================================


def _build_safe_builtins(log_fn: Callable[[str], None]) -> dict:
    """Build a restricted __builtins__ dict for the sandbox."""
    return {
        "True": True,
        "False": False,
        "None": None,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "isinstance": isinstance,
        "type": type,
        "print": log_fn,
        "abs": abs, "chr": chr, "ord": ord,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "reversed": reversed,
        "zip": zip,
        "map": map,
        "filter": filter,
        "any": any,
        "all": all,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
    }


def _default_agent_label(phase: str | None, index: int) -> str:
    return f"{phase} agent {index}" if phase else f"agent {index}"


def _build_agent_instructions(phase: str | None, options: AgentOptions) -> str | None:
    lines = []
    if phase:
        lines.append(f"Workflow phase: {phase}")
    if options.agent_type:
        lines.append(f"Act as workflow subagent type: {options.agent_type}")
    if options.isolation:
        lines.append(f"Requested isolation: {options.isolation}")
    if options.model:
        lines.append(f"Requested model: {options.model}")
    return "\n".join(lines) if lines else None


def _estimate_tokens(value: Any) -> int:
    return max(1, len(json_module.dumps(value if value is not None else "")) // 4)


def _normalize_agent_options(value: Any) -> AgentOptions:
    if value is None:
        return AgentOptions()
    if not isinstance(value, dict):
        raise TypeError("agent options must be a dict")
    return AgentOptions(
        label=_optional_str(value.get("label"), "agent label"),
        phase=_optional_str(value.get("phase"), "agent phase"),
        schema=value.get("schema"),
        model=_optional_str(value.get("model"), "agent model"),
        isolation=_optional_str(value.get("isolation"), "agent isolation"),
        agent_type=_optional_str(value.get("agentType") or value.get("agent_type"), "agent type"),
        agent=_optional_str(value.get("agent"), "agent name"),
    )


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, name)


def _assert_serializable(value: Any, name: str) -> None:
    try:
        json_module.dumps(value)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"{name} must be JSON-serializable; did you forget to await agent(), parallel(), pipeline(), or dag()? {e}"
        ) from e


# ============================================================================
# Runtime
# ============================================================================


async def run_workflow(script: str, options: WorkflowRunOptions | None = None) -> WorkflowRunResult:
    """
    Execute a workflow script in a sandbox.

    The script's meta assignment is parsed first, then the body is executed
    inside a restricted exec() context with agent(), parallel(), pipeline(),
    dag(), phase(), log(), args, cwd, and budget globals.
    """
    options = options or WorkflowRunOptions()
    started = time.monotonic()

    meta, body = parse_workflow_script(script)

    state = {
        "current_phase": None,
        "logs": [],
        "phases": [],
        "agent_count": 0,
        "spent": 0,
    }

    # Resolve agent runner: use injected one or create default
    agent_runner = options.agent
    if agent_runner is None:
        from .workflow_agent import WorkflowAgent as _WorkflowAgent

        agent_runner = _WorkflowAgent(
            cwd=options.cwd or os.getcwd(),
            model=options.model,
            model_registry=options.model_registry,
            auth_storage=options.auth_storage,
        )

    # Determine concurrency
    cpu_count = os.cpu_count() or 4
    default_concurrency = max(1, min(cpu_count - 2, 16))
    concurrency = max(1, min(options.concurrency or default_concurrency, 16))
    sem = asyncio.Semaphore(concurrency)

    signal = options.signal

    def _check_aborted():
        if signal and signal.is_set():
            raise asyncio.CancelledError("workflow aborted")

    # ── log ──
    def _log(message: str):
        text = str(message)
        state["logs"].append(text)

    # ── phase ──
    def _phase(title: str):
        _require_str(title, "phase title")
        state["current_phase"] = title
        if title not in state["phases"]:
            state["phases"].append(title)
        if options.on_phase:
            options.on_phase(title)

    # ── budget ──
    class _Budget:
        total = options.token_budget

        @staticmethod
        def spent():
            return state["spent"]

        @staticmethod
        def remaining():
            if _Budget.total is None:
                return float("inf")
            return max(0, _Budget.total - state["spent"])

    # ── agent ──
    async def _agent(prompt: Any, agent_opts: Any = None):
        _check_aborted()
        if _Budget.total is not None and _Budget.remaining() <= 0:
            raise RuntimeError("workflow token budget exhausted")

        task_prompt = _require_str(prompt, "agent prompt")
        norm_opts = _normalize_agent_options(agent_opts)
        assigned_phase = norm_opts.phase or state["current_phase"]
        requested_label = norm_opts.label.strip() if norm_opts.label else None

        # Resolve agent definition if name specified
        agent_active_tools = None
        agent_system_prompt = None
        agent_skill_names = None
        if norm_opts.agent:
            agent_defs = options.args.get("agent_defs", {}) if options.args else {}
            agent_def = agent_defs.get(norm_opts.agent)
            if agent_def:
                agent_active_tools = agent_def.get("tools")
                agent_system_prompt = agent_def.get("system_prompt")
                agent_skill_names = agent_def.get("skills") or None
                if not norm_opts.model and agent_def.get("model"):
                    norm_opts.model = agent_def["model"]

        async def _agent_runner():
            nonlocal requested_label
            state["agent_count"] += 1
            label = requested_label or _default_agent_label(assigned_phase, state["agent_count"])

            _check_aborted()

            if options.on_agent_start:
                options.on_agent_start({"label": label, "phase": assigned_phase, "prompt": task_prompt})

            try:
                instructions = _build_agent_instructions(assigned_phase, norm_opts)
                _log(f"agent [{label}] starting (phase={assigned_phase}, schema={'yes' if norm_opts.schema else 'no'}, agent={norm_opts.agent}, tools={agent_active_tools})")
                result = await agent_runner.run(
                    task_prompt,
                    label=label,
                    schema=norm_opts.schema,
                    instructions=instructions,
                    signal=signal,
                    event_callback=options.on_event,
                    active_tools=agent_active_tools,
                    system_prompt=agent_system_prompt,
                    skill_names=agent_skill_names,
                )
                _check_aborted()
                state["spent"] += _estimate_tokens(result)
                _log(f"agent [{label}] done: {str(result)[:120]}")

                if options.on_agent_end:
                    options.on_agent_end({"label": label, "phase": assigned_phase, "result": result, "error": None})

                return result
            except Exception as e:
                if signal and signal.is_set():
                    raise
                _log(f"agent [{label}] FAILED: {e}")
                import traceback as _tb
                _log(_tb.format_exc())

                if options.on_agent_end:
                    options.on_agent_end({"label": label, "phase": assigned_phase, "result": None, "error": str(e)})

                return None

        async with sem:
            return await _agent_runner()

    # ── parallel ──
    async def _parallel(thunks: list):
        _check_aborted()
        if not isinstance(thunks, list):
            raise TypeError("parallel() expects a list of functions")

        async def _safe_thunk(thunk, index):
            try:
                return await thunk()
            except Exception as e:
                if signal and signal.is_set():
                    raise
                _log(f"parallel[{index}] failed: {e}")
                return None

        return await asyncio.gather(*[_safe_thunk(t, i) for i, t in enumerate(thunks)])

    # ── pipeline ──
    async def _pipeline(items: list, *stages):
        _check_aborted()
        if not isinstance(items, list):
            raise TypeError("pipeline() expects a list as the first argument")

        async def _run_item(item, index):
            value = item
            for stage in stages:
                _check_aborted()
                try:
                    result = stage(value, item, index)
                    if asyncio.iscoroutine(result):
                        value = await result
                    else:
                        value = result
                except Exception as e:
                    if signal and signal.is_set():
                        raise
                    _log(f"pipeline[{index}] failed: {e}")
                    return None
            return value

        return await asyncio.gather(*[_run_item(item, i) for i, item in enumerate(items)])

    # ── dag ──
    async def _dag(tasks: list):
        """Execute tasks respecting DAG dependencies with maximum concurrency.

        Each task: {"id": str, "fn": callable, "depends_on": list[str]}
        Returns: dict mapping task id to its result (None if skipped or failed).
        """
        _check_aborted()
        if not isinstance(tasks, list):
            raise TypeError("dag() expects a list of task dicts")

        if not tasks:
            return {}

        # ---- Validate task structure and build lookup ----
        task_map: dict = {}
        for t in tasks:
            if not isinstance(t, dict):
                raise TypeError("each dag task must be a dict")
            tid = t.get("id")
            if not isinstance(tid, str) or not tid.strip():
                raise ValueError(f"each dag task must have a non-empty string 'id', got: {tid!r}")
            if tid in task_map:
                raise ValueError(f"duplicate dag task id: {tid!r}")
            fn = t.get("fn")
            if not callable(fn):
                raise ValueError(f"dag task '{tid}' must have a callable 'fn', got: {type(fn).__name__}")
            deps = t.get("depends_on", [])
            if not isinstance(deps, list):
                raise ValueError(f"dag task '{tid}' 'depends_on' must be a list")
            for d in deps:
                if not isinstance(d, str):
                    raise ValueError(f"dag task '{tid}' 'depends_on' entries must be strings, got: {d!r}")
            task_map[tid] = {"id": tid, "fn": fn, "depends_on": list(deps)}

        # ---- Validate all dependency references exist ----
        for tid, task in task_map.items():
            for dep in task["depends_on"]:
                if dep not in task_map:
                    raise ValueError(f"dag task '{tid}' depends on unknown task '{dep}'")

        # ---- Cycle detection: DFS with 3-color marking ----
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in task_map}

        def _find_cycle(tid, path):
            color[tid] = GRAY
            path.append(tid)
            for dep in task_map[tid]["depends_on"]:
                if color[dep] == GRAY:
                    idx = path.index(dep)
                    return path[idx:] + [dep]
                elif color[dep] == WHITE:
                    found = _find_cycle(dep, path[:])
                    if found:
                        return found
            color[tid] = BLACK
            return None

        for tid in task_map:
            if color[tid] == WHITE:
                cycle = _find_cycle(tid, [])
                if cycle:
                    raise ValueError(f"dag has a cycle: {' -> '.join(cycle)}")

        # ---- Kahn's algorithm with ready-queue for max parallelism ----
        in_degree = {tid: len(task["depends_on"]) for tid, task in task_map.items()}
        dependents = {tid: [] for tid in task_map}
        for tid, task in task_map.items():
            for dep in task["depends_on"]:
                dependents[dep].append(tid)

        results: dict[str, Any] = {}
        failed: set[str] = set()

        ready = [tid for tid, deg in in_degree.items() if deg == 0]

        while ready:
            async def _run_one(tid):
                _check_aborted()
                task = task_map[tid]

                # Check if any dependency failed -> skip this task
                for dep in task["depends_on"]:
                    if dep in failed:
                        _log(f"dag[{tid}] skipped: dependency '{dep}' failed")
                        failed.add(tid)
                        return tid, None

                try:
                    result = await task["fn"]()
                    if result is None:
                        _log(f"dag[{tid}] failed: returned None")
                        failed.add(tid)
                    return tid, result
                except Exception as e:
                    if signal and signal.is_set():
                        raise
                    _log(f"dag[{tid}] failed: {e}")
                    import traceback as _tb
                    _log(_tb.format_exc())
                    failed.add(tid)
                    return tid, None

            batch = await asyncio.gather(*[_run_one(t) for t in ready])

            next_ready = []
            for tid, result in batch:
                results[tid] = result
                for dep_tid in dependents[tid]:
                    in_degree[dep_tid] -= 1
                    if in_degree[dep_tid] == 0:
                        next_ready.append(dep_tid)
            ready = next_ready

        # Mark any remaining unprocessed tasks as None (all are skipped descendants)
        for tid in task_map:
            if tid not in results:
                results[tid] = None

        return results

    # ── Build sandbox ──
    sandbox_globals: dict[str, Any] = {
        "agent": _agent,
        "parallel": _parallel,
        "pipeline": _pipeline,
        "dag": _dag,
        "log": _log,
        "phase": _phase,
        "args": options.args,
        "cwd": options.cwd or os.getcwd(),
        "budget": _Budget(),
        "JSON": json_module,
        "Math": math,
        "Array": list,
        "Object": dict,
        "Map": dict,
        "Set": set,
        "__builtins__": _build_safe_builtins(_log),
    }

    # ── Execute ──
    wrapper = f"async def __workflow__():\n" + "\n".join(f"  {line}" for line in body.split("\n"))
    local_vars: dict[str, Any] = {}
    exec(wrapper, sandbox_globals, local_vars)
    result = await local_vars["__workflow__"]()

    _assert_serializable(result, "workflow result")

    return WorkflowRunResult(
        meta=meta,
        result=result,
        logs=state["logs"],
        phases=state["phases"],
        agent_count=state["agent_count"],
        duration_ms=(time.monotonic() - started) * 1000,
    )
