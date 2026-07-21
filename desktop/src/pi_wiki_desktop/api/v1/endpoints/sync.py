"""Single-agent sync endpoints (original mode)."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from ....config import load_projects
from ....models import SyncAllResult, SyncRequest, SyncResult
from ....sessions.factory import get_model_registry, get_or_create_session, WikiSessionOptions
from pi_wiki_agent.vcs import create_monitor

router = APIRouter()


@router.post("/projects/{name}/sync/{rev}", response_model=SyncResult)
async def sync_commit(name: str, rev: str, body: SyncRequest | None = None,
                      registry = Depends(get_model_registry)):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)

    ws = get_or_create_session(
        WikiSessionOptions.from_model_str(cfg["path"], body.model if body else None),
        registry,
    )
    try:
        result = await ws.sync_from_commit(
            changed_files=commit.files, commit_message=commit.message, diff=commit.diff,
            author=commit.author,
        )
        await monitor.mark_processed(rev)
        return SyncResult(revision=rev, success=True, wiki_pages_modified=result.wiki_pages_modified)
    except Exception as exc:
        return SyncResult(revision=rev, success=False, wiki_pages_modified=[], error=str(exc))


@router.post("/projects/{name}/sync/{rev}/stream")
async def sync_commit_stream(name: str, rev: str, body: SyncRequest | None = None,
                             registry = Depends(get_model_registry)):
    logger.info("==========>单agent-stream分支==================")
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    ws = get_or_create_session(
        WikiSessionOptions.from_model_str(cfg["path"], body.model if body else None),
        registry,
    )

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_agent_event(event):
        evt = {"type": event.type}
        try:
            if event.type == "message_start":
                msg = event.message
                if msg and hasattr(msg, "role"):
                    evt["role"] = msg.role
            elif event.type == "message_update":
                ae = event.assistant_message_event
                if ae and hasattr(ae, "delta"):
                    evt["text"] = ae.delta
            elif event.type == "tool_execution_start":
                evt["tool"] = event.tool_name
                evt["args"] = str(getattr(event, "args", ""))[:120]
            elif event.type == "tool_execution_end":
                evt["tool"] = event.tool_name
                evt["is_error"] = getattr(event, "is_error", False)
        except Exception:
            pass
        queue.put_nowait(evt)

    ws.subscribe(on_agent_event)

    async def _run_sync():
        try:
            result = await ws.sync_from_commit(
                changed_files=commit.files, commit_message=commit.message, diff=commit.diff,
            )
            await monitor.mark_processed(rev)
            await queue.put({"type": "sync_done", "pages": result.wiki_pages_modified, "success": True})
        except Exception as exc:
            await queue.put({"type": "sync_done", "success": False, "error": str(exc)})

    task = asyncio.create_task(_run_sync())

    async def _event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=120)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") in ("sync_done",):
                    await task
                    return
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                return

    return StreamingResponse(
        _event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{name}/sync-all", response_model=SyncAllResult)
async def sync_all_commits(name: str, body: SyncRequest | None = None,
                           registry = Depends(get_model_registry)):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commits = await monitor.poll()

    ws = get_or_create_session(
        WikiSessionOptions.from_model_str(cfg["path"], body.model if body else None),
        registry,
    )
    results: list[SyncResult] = []
    for c in commits:
        try:
            full = await monitor.get_commit(c.revision)
            result = await ws.sync_from_commit(
                changed_files=full.files, commit_message=full.message, diff=full.diff,
            )
            await monitor.mark_processed(c.revision)
            results.append(SyncResult(revision=c.revision, success=True, wiki_pages_modified=result.wiki_pages_modified))
        except Exception as exc:
            results.append(SyncResult(revision=c.revision, success=False, wiki_pages_modified=[], error=str(exc)))
    return SyncAllResult(processed=len(results), results=results)
