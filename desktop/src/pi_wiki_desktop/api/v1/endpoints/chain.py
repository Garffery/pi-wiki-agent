"""Chain sync endpoints (multi-agent mode)."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from ....config import load_projects
from ....models import ChainStepResult, ChainSyncRequest, ChainSyncResult
from ....sessions.factory import get_model_registry, make_chain_session_factory
from pi_wiki_agent.vcs import create_monitor

router = APIRouter()


@router.post("/projects/{name}/chain-sync/{rev}", response_model=ChainSyncResult)
async def chain_sync_commit(name: str, rev: str, body: ChainSyncRequest | None = None,
                            registry = Depends(get_model_registry)):
    logger.info("==========>chain分支==================")
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)

    from pi_wiki_agent.core.chain import execute_sync_chain

    try:
        result = await execute_sync_chain(
            project_path=cfg["path"],
            changed_files=commit.files, commit_message=commit.message, diff=commit.diff, revision=rev,
            session_factory=make_chain_session_factory(registry, body.model if body else None),
        )
        await monitor.mark_processed(rev)
        steps = [ChainStepResult(agent=s.agent, step_index=s.step_index, output=s.output,
                                  exit_code=s.exit_code, error=s.error) for s in result.steps]
        return ChainSyncResult(success=result.success, error=result.error, steps=steps, last_output=result.last_output)
    except Exception as exc:
        return ChainSyncResult(success=False, error=str(exc))


@router.post("/projects/{name}/chain-sync/{rev}/stream")
async def chain_sync_commit_stream(name: str, rev: str, body: ChainSyncRequest | None = None,
                                   registry = Depends(get_model_registry)):
    logger.info("==========>chain-stream分支==================")
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    logger.info("========>提交版本:{}",rev)

    queue: asyncio.Queue[dict] = asyncio.Queue()


    def on_chain_progress(step_index: int, agent_name: str, event_type: str, data: dict):
        if event_type == "agent_event":
            queue.put_nowait(data)
        else:
            queue.put_nowait({
                "type": f"chain_{event_type}", "step_index": step_index,
                "agent": agent_name, "data": data,
            })

    async def _run_chain():
        from pi_wiki_agent.core.chain import execute_sync_chain
        try:
            result = await execute_sync_chain(
                project_path=cfg["path"],
                changed_files=commit.files, commit_message=commit.message, diff=commit.diff, revision=rev,
                on_progress=on_chain_progress, session_factory=make_chain_session_factory(registry, body.model if body else None),
            )
            await monitor.mark_processed(rev)
            await queue.put({
                "type": "chain_done", "success": result.success,
                "steps": [{"agent": s.agent, "step_index": s.step_index,
                            "exit_code": s.exit_code, "error": s.error} for s in result.steps],
                "last_output": result.last_output,
            })
        except Exception as exc:
            await queue.put({"type": "chain_done", "success": False, "error": str(exc)})

    task = asyncio.create_task(_run_chain())

    async def _event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") in ("chain_done",):
                    await task; return
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"; return

    return StreamingResponse(
        _event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
