"""Workflow-based wiki sync endpoints.

New endpoint: POST /projects/{name}/workflow-sync/{rev}/stream

Parallel to chain.py — uses the workflow engine instead of the sequential chain.
The existing chain-sync endpoints are untouched.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from ....config import load_projects
from ....sessions.factory import get_model_registry
from pi_wiki_agent.vcs import create_monitor

router = APIRouter()


class WorkflowSyncRequest(BaseModel):
    model: str | None = None
    workflow: str | None = None  # workflow script name, defaults to "sync.yaml"
    keep_checkpoint: bool = False  # if True, skip checkpoint cleanup (for testing)


@router.post("/projects/{name}/workflow-sync/{rev}/stream")
async def workflow_sync_commit_stream(
    name: str,
    rev: str,
    body: WorkflowSyncRequest | None = None,
    registry=Depends(get_model_registry),
):
    """Execute wiki sync using the workflow engine.

    This is the parallel-agent alternative to chain-sync/stream.
    """
    logger.info("==========> workflow-sync stream ==================")

    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    logger.info("========> 提交版本: {}", rev)

    # Load pre-written workflow script
    script_name = body.workflow if body and body.workflow else "sync.yaml"
    if script_name and "." not in script_name:
        script_name += ".yaml"
    script = _load_workflow_script(cfg["path"], script_name)

    queue: asyncio.Queue[dict] = asyncio.Queue()

    # ── Progress → SSE ──
    def on_agent_start(data: dict):
        logger.info("[SSE] agent_start: label={}, phase={}", data.get("label"), data.get("phase"))
        queue.put_nowait({
            "type": "workflow_agent_start",
            "label": data.get("label", ""),
            "phase": data.get("phase", ""),
        })

    def on_agent_end(data: dict):
        logger.info("[SSE] agent_end: label={}, phase={}, error={}", data.get("label"), data.get("phase"), data.get("error"))
        queue.put_nowait({
            "type": "workflow_agent_end",
            "label": data.get("label", ""),
            "phase": data.get("phase", ""),
            "error": data.get("error"),
        })

    def on_phase(title: str):
        logger.info("[SSE] phase: {}", title)
        queue.put_nowait({"type": "workflow_phase", "phase": title})

    def on_event(evt: dict):
        # Forward subagent internal events directly (same format as chain agent_event)
        queue.put_nowait(evt)

    # ── Run ──
    async def _run_workflow():
        logger.info("开始运行======run_workflow")
        from pi_wiki_agent.core.workflow_sync import execute_workflow_sync
        from pi_coding_agent.core.auth_storage import AuthStorage

        keep_checkpoint_flag = body.keep_checkpoint if body else False

        try:
            result = await execute_workflow_sync(
                project_path=cfg["path"],
                changed_files=commit.files,
                commit_message=commit.message,
                diff=commit.diff,
                revision=rev,
                script=script,
                model=body.model if body else None,
                model_registry=registry,
                auth_storage=AuthStorage(),
                on_agent_start=on_agent_start,
                on_agent_end=on_agent_end,
                on_phase=on_phase,
                on_event=on_event,
                keep_checkpoint=keep_checkpoint_flag,
            )
            await monitor.mark_processed(rev)
            await queue.put({
                "type": "workflow_done",
                "success": True,
                "phases": result.phases,
                "agent_count": result.agent_count,
                "duration_ms": result.duration_ms,
                "logs": result.logs,
                "result": result.result,
            })
        except Exception as exc:
            logger.error("Workflow sync failed: {}\n{}", exc, traceback.format_exc())
            await queue.put({
                "type": "workflow_done",
                "success": False,
                "error": str(exc),
            })

    task = asyncio.create_task(_run_workflow())

    async def _event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") in ("workflow_done",):
                    await task
                    return
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                return

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_json(path: str) -> dict | None:
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


@router.get("/projects/{name}/workflow-failures")
def get_workflow_failures(name: str):
    """List all unfinished workflow runs with checkpoints remaining."""
    from datetime import datetime

    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    project_path = cfg["path"]
    cp_base = os.path.join(project_path, '.wiki', 'checkpoints')
    if not os.path.isdir(cp_base):
        return {"failures": []}

    monitor = create_monitor(project_path)
    failures = []

    for namespace in sorted(os.listdir(cp_base), reverse=True):
        ns_dir = os.path.join(cp_base, namespace)
        if not os.path.isdir(ns_dir):
            continue

        meta = _load_json(os.path.join(ns_dir, '_meta.json'))
        analysis = _load_json(os.path.join(ns_dir, 'analysis.json'))
        plan = _load_json(os.path.join(ns_dir, 'plan.json'))
        write_results = _load_json(os.path.join(ns_dir, 'write_results.json'))
        wr_value = (write_results or {}).get('value', {})

        analysis_done = analysis is not None and analysis.get('value') is not None
        plan_done = plan is not None and plan.get('value') is not None
        wr_values = [v for v in wr_value.values() if isinstance(v, dict)]
        wr_total = len(wr_values)
        wr_completed = sum(1 for v in wr_values if v.get('value') is not None)
        wr_failed = sum(1 for v in wr_values if v.get('value') is None)
        wr_done = wr_total > 0 and wr_failed == 0

        # Skip fully completed runs
        if analysis_done and plan_done and wr_done:
            continue

        # Try to get commit message
        commit_msg = None
        try:
            commit = monitor.get_commit_sync(namespace)
            commit_msg = commit.message if commit else None
        except Exception:
            pass

        mtimes = [os.path.getmtime(os.path.join(ns_dir, f)) for f in os.listdir(ns_dir)]
        updated_at = datetime.fromtimestamp(max(mtimes)).isoformat() if mtimes else None

        failures.append({
            "revision": namespace,
            "commit_message": commit_msg,
            "workflow": (meta or {}).get("workflow", "sync_commit"),
            "phases": {
                "analysis": {"done": analysis_done},
                "plan": {"done": plan_done},
                "write_results": {"done": wr_done, "completed": wr_completed, "total": wr_total, "failed": wr_failed},
            },
            "updated_at": updated_at,
        })

    return {"failures": failures}


@router.delete("/projects/{name}/workflow-sync/{rev}/checkpoint")
def clear_checkpoint(name: str, rev: str):
    """Clear checkpoint for a specific commit, forcing a fresh run next time."""
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    project_path = cfg["path"]
    ns_dir = os.path.join(project_path, '.wiki', 'checkpoints', rev)
    if os.path.isdir(ns_dir):
        shutil.rmtree(ns_dir)
    return {"cleared": True, "namespace": rev}


def _load_workflow_script(project_path: str, script_name: str) -> str:
    """Load a workflow script from .wiki/workflows/ or fall back to built-in."""
    from pathlib import Path

    # 1. Try project-local script
    local = Path(project_path) / ".wiki" / "workflows" / script_name
    if local.exists():
        return local.read_text(encoding="utf-8")

    # 2. Fall back to built-in script (in wiki-agent package)
    import pi_wiki_agent.core.workflow.scripts as _scripts_pkg
    builtin = Path(_scripts_pkg.__file__).parent / script_name if hasattr(_scripts_pkg, '__file__') else None
    if builtin and builtin.exists():
        logger.info("Using built-in workflow script: {}", builtin)
        return builtin.read_text(encoding="utf-8")

    raise HTTPException(400, f"Workflow script not found: {script_name}")
