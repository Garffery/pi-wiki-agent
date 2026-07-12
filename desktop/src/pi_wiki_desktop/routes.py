"""API routes for wiki management desktop app."""

from __future__ import annotations

from pathlib import Path

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pi_wiki_agent import WikiSession
from pi_wiki_agent.vcs import CommitInfo, create_monitor

from .config import add_project, load_projects, remove_project
from .wiki_model_registry import WikiModelRegistry
from pi_wiki_agent.filter import FilterRule
from .models import (
    AffectInfo,
    CommitDetail,
    CommitSummary,
    HealthResponse,
    ModelConfigCreate,
    ProjectCreate,
    ProjectInfo,
    SyncAllResult,
    SyncRequest,
    SyncResult,
)

router = APIRouter(prefix="/api")


_registry: WikiModelRegistry | None = None


def _get_registry() -> WikiModelRegistry:
    global _registry
    if _registry is None:
        from .wiki_model_registry import WikiModelRegistry
        _registry = WikiModelRegistry()
    return _registry


def _get_or_create_session(project_path: str, model: str | None = None) -> WikiSession:
    """Create a WikiSession, optionally with a specific model (format: 'provider:model_id')."""
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")

    # Get pre-loaded extensions from app startup bootstrap
    from .app import _get_resource_store
    store = _get_resource_store()
    extra_tools = store.get("extension_tools", [])
    extension_runner = store.get("extension_runner")

    if model and ":" in model:
        provider, model_id = model.split(":", 1)
        registry = _get_registry()
        try:
            ai_model = registry.resolve_model(model_id=model_id, provider=provider)
            return WikiSession(project_path, model=ai_model,
                               extra_tools=extra_tools, extension_runner=extension_runner)
        except Exception:
            pass  # fall through to default

    return WikiSession(project_path, extra_tools=extra_tools, extension_runner=extension_runner)


def _commit_to_summary(c: CommitInfo) -> CommitSummary:
    return CommitSummary(
        revision=c.revision,
        message=c.message,
        author=c.author,
        timestamp=c.timestamp,
        files=list(c.files),
    )


def _commit_to_detail(c: CommitInfo, affected: dict) -> CommitDetail:
    detail_affected: dict[str, list[AffectInfo]] = {}
    for page, entries in affected.items():
        detail_affected[page] = [
            AffectInfo(file=e.file, wiki_page=e.wiki_page, section_id=e.section_id)
            for e in entries
        ]
    return CommitDetail(
        revision=c.revision,
        message=c.message,
        author=c.author,
        timestamp=c.timestamp,
        files=list(c.files),
        diff=c.diff,
        affected=detail_affected,
    )


# ── Health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


# ── Projects CRUD ────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectInfo])
async def list_projects():
    projects = load_projects()
    result: list[ProjectInfo] = []
    for name, cfg in projects.items():
        try:
            monitor = create_monitor(cfg["path"])
            pending = await monitor.poll()
            result.append(ProjectInfo(
                name=name,
                path=cfg["path"],
                vcs=cfg.get("vcs", "unknown"),
                last_revision=monitor.get_last_revision(),
                pending_commits=len(pending),
            ))
        except Exception as exc:
            result.append(ProjectInfo(
                name=name,
                path=cfg["path"],
                vcs=cfg.get("vcs", "unknown"),
                last_revision=f"error: {exc}",
                pending_commits=0,
            ))
    return result


@router.post("/projects", response_model=dict)
async def create_project(body: ProjectCreate):
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(400, f"路径不存在: {body.path}")
    if not (p / ".wiki").exists():
        raise HTTPException(400, f"项目缺少 .wiki 目录: {body.path}")
    add_project(body.name, str(p.absolute()))
    return {"name": body.name, "path": str(p.absolute())}


@router.delete("/projects/{name}", response_model=dict)
async def delete_project(name: str):
    if not remove_project(name):
        raise HTTPException(404, f"项目不存在: {name}")
    return {"deleted": name}


# ── Commits ──────────────────────────────────────────────────────────────

@router.get("/projects/{name}/commits", response_model=list[CommitSummary])
async def list_commits(name: str):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commits = await monitor.poll()
    return [_commit_to_summary(c) for c in commits]


@router.get("/projects/{name}/commits/{rev}", response_model=CommitDetail)
async def get_commit_detail(name: str, rev: str):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    ws = _get_or_create_session(cfg["path"])
    result = await ws.sync_from_commit(
        changed_files=commit.files,
        commit_message=commit.message,
        diff=commit.diff,
        dry_run=True,
    )
    return _commit_to_detail(commit, result.affected)


# ── Models ───────────────────────────────────────────────────────────────

@router.get("/models", response_model=list[dict])
async def list_models():
    """List all available models (built-in with auth + custom from models.json)."""
    registry = _get_registry()
    return await registry.get_available_summaries()


@router.post("/models", response_model=dict)
async def create_model(body: ModelConfigCreate):
    """Add a custom model to ~/.pi/agent/models.json."""
    registry = _get_registry()
    registry.add_custom_model(
        name=body.name, provider=body.provider,
        model_id=body.model_id, base_url=body.base_url,
        api_key=body.api_key,
    )
    return {"status": "ok", "name": body.name}


@router.delete("/models/{provider}/{model_id}", response_model=dict)
async def delete_model(provider: str, model_id: str):
    """Remove a custom model from ~/.pi/agent/models.json."""
    registry = _get_registry()
    if not registry.remove_custom_model(provider, model_id):
        raise HTTPException(404, f"模型不存在: {provider}:{model_id}")
    return {"deleted": f"{provider}:{model_id}"}


# ── Filters ─────────────────────────────────────────────────────────────

@router.get("/projects/{name}/filters", response_model=list[dict])
async def get_filters(name: str):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    from pi_wiki_agent.filter import FilterManager
    fm = FilterManager(cfg["path"])
    rules = fm.get_rules()
    return [
        {"index": i, "type": r.type, "pattern": r.pattern, "description": r.description}
        for i, r in enumerate(rules)
    ]


@router.post("/projects/{name}/filters", response_model=dict)
async def add_filter(name: str, body: dict):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    from pi_wiki_agent.filter import FilterManager
    fm = FilterManager(cfg["path"])
    rule = FilterRule(
        type=body.get("type", "path"),
        pattern=body.get("pattern", ""),
        description=body.get("description", ""),
    )
    fm.add_rule(rule)
    return {"status": "ok"}


@router.delete("/projects/{name}/filters/{index}", response_model=dict)
async def remove_filter(name: str, index: int):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    from pi_wiki_agent.filter import FilterManager
    fm = FilterManager(cfg["path"])
    if not fm.remove_rule(index):
        raise HTTPException(404, "规则索引无效")
    return {"deleted": index}


@router.put("/projects/{name}/filters/toggle", response_model=dict)
async def toggle_filter(name: str, body: dict):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    from pi_wiki_agent.filter import FilterManager
    fm = FilterManager(cfg["path"])
    enabled = body.get("enabled", True)
    fm.set_enabled(enabled)
    return {"enabled": enabled}


# ── Sync ─────────────────────────────────────────────────────────────────

@router.post("/projects/{name}/sync/{rev}", response_model=SyncResult)
async def sync_commit(name: str, rev: str, body: SyncRequest | None = None):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)

    ws = _get_or_create_session(cfg["path"], model=body.model if body else None)
    try:
        result = await ws.sync_from_commit(
            changed_files=commit.files,
            commit_message=commit.message,
            diff=commit.diff,
        )
        await monitor.mark_processed(rev)
        return SyncResult(
            revision=rev,
            success=True,
            wiki_pages_modified=result.wiki_pages_modified,
        )
    except Exception as exc:
        return SyncResult(
            revision=rev,
            success=False,
            wiki_pages_modified=[],
            error=str(exc),
        )


@router.post("/projects/{name}/sync/{rev}/stream")
async def sync_commit_stream(name: str, rev: str, body: SyncRequest | None = None):
    """Stream sync progress via SSE."""
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    ws = _get_or_create_session(cfg["path"], model=body.model if body else None)

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
                changed_files=commit.files,
                commit_message=commit.message,
                diff=commit.diff,
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
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{name}/sync-all", response_model=SyncAllResult)
async def sync_all_commits(name: str, body: SyncRequest | None = None):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commits = await monitor.poll()

    ws = _get_or_create_session(cfg["path"], model=body.model if body else None)
    results: list[SyncResult] = []
    for c in commits:
        try:
            full = await monitor.get_commit(c.revision)
            result = await ws.sync_from_commit(
                changed_files=full.files,
                commit_message=full.message,
                diff=full.diff,
            )
            await monitor.mark_processed(c.revision)
            results.append(SyncResult(
                revision=c.revision,
                success=True,
                wiki_pages_modified=result.wiki_pages_modified,
            ))
        except Exception as exc:
            results.append(SyncResult(
                revision=c.revision,
                success=False,
                wiki_pages_modified=[],
                error=str(exc),
            ))

    return SyncAllResult(processed=len(results), results=results)
