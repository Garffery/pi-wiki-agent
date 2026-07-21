"""Project CRUD endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ....config import add_project, load_projects, remove_project
from ....models import ProjectCreate, ProjectInfo
from pi_wiki_agent.vcs import create_monitor

router = APIRouter()


@router.get("/projects", response_model=list[ProjectInfo])
async def list_projects():
    projects = load_projects()
    result: list[ProjectInfo] = []
    for name, cfg in projects.items():
        try:
            monitor = create_monitor(cfg["path"])
            pending = await monitor.poll()
            # Exclude commits with all files filtered
            from pi_wiki_agent.indexer import WikiIndexer
            indexer = WikiIndexer(cfg["path"])
            visible = [c for c in pending if indexer.filter.should_include_commit(c.files, c.message, c.author)]
            from pi_wiki_agent.core.chain.generation_plan import has_wiki_pages, GenerationPlan
            result.append(ProjectInfo(
                name=name,
                path=cfg["path"],
                vcs=cfg.get("vcs", "unknown"),
                last_revision=monitor.get_last_revision(),
                pending_commits=len(visible),
                has_wiki=has_wiki_pages(cfg["path"]),
                has_generation_plan=GenerationPlan.load(cfg["path"]) is not None,
            ))
        except Exception as exc:
            result.append(ProjectInfo(
                name=name, path=cfg["path"], vcs=cfg.get("vcs", "unknown"),
                last_revision=f"error: {exc}", pending_commits=0,
                has_wiki=False, has_generation_plan=False,
            ))
    return result


DEFAULT_LOOKBACK = 50


async def _resolve_start_revision(project_path: str, explicit: str) -> str:
    """Resolve the starting revision for a new project.

    If an explicit revision is provided, use it directly.
    Otherwise, look back DEFAULT_LOOKBACK commits from HEAD.
    """
    if explicit:
        return explicit
    try:
        from pi_wiki_agent.vcs import create_monitor as _create_monitor
        monitor = _create_monitor(project_path)
        return await monitor.get_nth_ancestor(DEFAULT_LOOKBACK)
    except Exception:
        return ""


@router.post("/projects", response_model=dict)
async def create_project(body: ProjectCreate):
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(400, f"路径不存在: {body.path}")
    if not (p / ".wiki").exists():
        raise HTTPException(400, f"项目缺少 .wiki 目录: {body.path}")
    add_project(body.name, str(p.absolute()))
    start_rev = await _resolve_start_revision(str(p.absolute()), body.start_revision)
    if start_rev:
        try:
            monitor = create_monitor(str(p.absolute()))
            await monitor.mark_processed(start_rev)
        except Exception:
            pass
    return {"name": body.name, "path": str(p.absolute())}


@router.delete("/projects/{name}", response_model=dict)
async def delete_project(name: str):
    if not remove_project(name):
        raise HTTPException(404, f"项目不存在: {name}")
    return {"deleted": name}
