"""
Workflow-based wiki sync — replaces the sequential chain with a pre-written
workflow script, enabling parallel wiki-writer agents.

Usage::

    script = Path(".wiki/workflows/sync.yaml").read_text()
    result = await execute_workflow_sync(
        project_path="/data/my-project",
        changed_files=["src/auth.py"],
        commit_message="feat: oauth",
        diff="...",
        revision="abc123",
        script=script,
    )
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pi_wiki_agent.vcs import create_monitor

from pi_wiki_agent.logging import logger
from pi_wiki_agent.indexer import WikiIndexer
from pi_wiki_agent.core.chain.wiki_chain import _format_affected_sections


async def execute_workflow_sync(
    project_path: str,
    changed_files: list[str],
    commit_message: str,
    diff: str,
    revision: str,
    script: str,
    model: Any = None,
    model_registry: Any = None,
    auth_storage: Any = None,
    on_agent_start: Any = None,
    on_agent_end: Any = None,
    on_phase: Any = None,
    on_event: Any = None,
    keep_checkpoint: bool = False,
    extra_args: dict | None = None,
) -> Any:
    """Execute a wiki sync using a workflow script.

    Parameters
    ----------
    project_path:
        Project root directory.
    changed_files:
        List of changed files from the VCS commit.
    commit_message:
        The commit message.
    diff:
        Full unified diff of the commit.
    revision:
        Commit revision hash.
    script:
        Workflow script text (read from .wiki/workflows/*.py).
    model:
        Optional model override.
    model_registry:
        Optional model registry for resolving API keys.
    auth_storage:
        Optional auth storage.

    Returns
    -------
    WorkflowRunResult
    """
    from .workflow import WorkflowRunOptions, run_workflow

    logger.info("execute_workflow_sync start: project={}, files={}, rev={}",
                project_path, len(changed_files) if changed_files else 0, revision)

    # ── 0. Validate inputs ─────────────────────────────────────────────────
    if not changed_files:
        raise ValueError("changed_files is empty or None")
    if commit_message is None:
        commit_message = ""
    if diff is None:
        diff = ""

    # ── 1. Reverse index: which wiki sections are affected ──────────────────
    indexer = WikiIndexer(project_path)
    affected = indexer.get_affected_sections(changed_files) or {}
    affected_text = _format_affected_sections(affected)

    logger.info(
        "Workflow sync: {} changed files → {} affected wiki pages",
        len(changed_files), len(affected),
    )

    # ── 2. Ensure chain working directory ───────────────────────────────────
    chain_dir = os.path.join(project_path, ".wiki", "chain")
    os.makedirs(chain_dir, exist_ok=True)

    # ── 3. Write per-file diffs (isolated by revision) ─────────────────────
    diffs_dir = os.path.join(chain_dir, "diffs", revision)
    monitor = create_monitor(project_path)
    await monitor.write_file_diffs(revision, changed_files, diffs_dir)

    # ── 4. Load workflow agent definitions ─────────────────────────────────
    agent_defs = _load_workflow_agent_defs(project_path)
    logger.info("Loaded {} workflow agent defs: {}", len(agent_defs), list(agent_defs.keys()))

    # ── 5. Build args for the workflow script ──────────────────────────────
    args = {
        "project_path": project_path,
        "changed_files": changed_files,
        "commit_message": commit_message,
        "diff": diff,
        "affected_sections": affected_text,
        "diffs_dir": diffs_dir,
        "revision": revision,
        "commit_hash": revision,
        "agent_defs": agent_defs,
        "keep_checkpoint": keep_checkpoint,
    }
    if extra_args:
        args.update(extra_args)

    # ── 6. Resolve model string → Model object ────────────────────────────
    resolved_model = _resolve_model(model, model_registry)
    logger.info(
        "Workflow sync model: input={}, resolved={}/{}",
        model,
        type(resolved_model).__name__ if resolved_model else "None",
        f"{resolved_model.provider}:{resolved_model.id}" if resolved_model and hasattr(resolved_model, "provider") else "N/A",
    )

    # ── 7. Compile YAML → Python ──────────────────────────────────────────
    from .workflow.ast_compiler import compile_workflow_yaml
    script = compile_workflow_yaml(script, agent_defs)
    logger.info("Compiled YAML workflow → {} bytes Python script", len(script))

    # ── 8. Create WorkflowAgent ────────────────────────────────────────────
    from .workflow import WorkflowAgent

    agent = WorkflowAgent(
        cwd=project_path,
        model=resolved_model,
        model_registry=model_registry,
        auth_storage=auth_storage,
    )

    # ── 9. Execute ─────────────────────────────────────────────────────────
    result = await run_workflow(
        script,
        WorkflowRunOptions(
            args=args,
            cwd=project_path,
            agent=agent,
            concurrency=8,
            on_agent_start=on_agent_start,
            on_agent_end=on_agent_end,
            on_phase=on_phase,
            on_event=on_event,
        ),
    )
    logger.info("工作流的最终结果:{}",result)

    # ── 10. Cleanup temp diffs ─────────────────────────────────────────────
    import shutil
    try:
        shutil.rmtree(diffs_dir)
    except OSError:
        pass

    return result


def _load_workflow_agent_defs(project_path: str) -> dict:
    """Load workflow agent definitions with project override.

    Priority:
      1. <project>/.wiki/workflows/agents/*.md
      2. builtin-agents/*.md  (packaged with workflow engine)

    Returns dict of {agent_name: {tools, system_prompt, model, skills, thinking}}.
    """
    from pi_coding_agent.utils.frontmatter import parse_frontmatter

    builtin_dir = os.path.join(os.path.dirname(__file__), "workflow", "builtin-agents")
    project_dir = os.path.join(project_path, ".wiki", "workflows", "agents")

    def _load_dir(directory: str) -> dict:
        result = {}
        if not os.path.isdir(directory):
            return result
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(directory, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    frontmatter, body = parse_frontmatter(fh.read())
                name = frontmatter.get("name") or Path(fname).stem
                tools = frontmatter.get("tools")
                if tools is None:
                    tools_raw = frontmatter.get("tool")
                    if tools_raw:
                        tools = [tools_raw] if isinstance(tools_raw, str) else tools_raw
                elif isinstance(tools, str):
                    tools = [t.strip() for t in tools.split(",") if t.strip()]
                result[name] = {
                    "tools": tools,
                    "system_prompt": body.strip() or None,
                    "model": frontmatter.get("model"),
                    "skills": frontmatter.get("skills") or [],
                    "thinking": frontmatter.get("thinking"),
                }
            except Exception:
                logger.warning("Failed to load workflow agent def: {}", fpath)
        return result

    # Builtin first, then project overrides
    agent_defs = _load_dir(builtin_dir)
    project_defs = _load_dir(project_dir)
    agent_defs.update(project_defs)
    return agent_defs


def load_workflow_script(project_path: str, script_name: str = "sync.yaml") -> str:
    """Load a workflow script from .wiki/workflows/ (YAML format).

    Parameters
    ----------
    project_path:
        Project root directory.
    script_name:
        Script filename (default: sync.yaml).

    Returns
    -------
    The raw YAML text (will be compiled to Python by execute_workflow_sync).
    """
    script_path = Path(project_path) / ".wiki" / "workflows" / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Workflow script not found: {script_path}")
    return script_path.read_text(encoding="utf-8")


def _resolve_model(model: Any, model_registry: Any) -> Any:
    """Resolve a model string like 'provider:model_id' to a Model object."""
    if model is None:
        return None
    # Already a Model object
    if hasattr(model, "id") and hasattr(model, "provider"):
        return model
    # String format: "provider:model_id"
    if isinstance(model, str) and ":" in model:
        provider, model_id = model.split(":", 1)
        if model_registry is not None:
            try:
                return model_registry.resolve_model(model_id=model_id, provider=provider)
            except Exception:
                pass
        logger.warning("Failed to resolve model '{}', using default", model)
        return None
    return None
