"""Filter management endpoints."""

from fastapi import APIRouter, HTTPException

from ....config import load_projects
from pi_wiki_agent.filter import FilterRule

router = APIRouter()


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
