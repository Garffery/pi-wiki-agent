"""Commit listing and detail endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ....config import load_projects
from ....models import CommitDetail, CommitSummary, AffectInfo
from ....sessions.factory import get_model_registry, get_or_create_session, WikiSessionOptions
from pi_wiki_agent.indexer import WikiIndexer
from pi_wiki_agent.vcs import CommitInfo, create_monitor
from loguru import logger
router = APIRouter()


def _commit_to_summary(c: CommitInfo) -> CommitSummary:
    return CommitSummary(
        revision=c.revision, message=c.message, author=c.author,
        timestamp=c.timestamp, files=list(c.files),
    )


def _commit_to_detail(c: CommitInfo, affected: dict, filtered_diff: str) -> CommitDetail:
    detail_affected: dict[str, list[AffectInfo]] = {}
    for page, entries in affected.items():
        detail_affected[page] = [
            AffectInfo(file=e.file, wiki_page=e.wiki_page, section_id=e.section_id)
            for e in entries
        ]
    return CommitDetail(
        revision=c.revision, message=c.message, author=c.author,
        timestamp=c.timestamp, files=list(c.files),
        diff=filtered_diff, affected=detail_affected,
    )


@router.get("/projects/{name}/commits", response_model=list[CommitSummary])
async def list_commits(name: str):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commits = await monitor.poll()

    # Exclude commits filtered out by path, message, or author rules
    indexer = WikiIndexer(cfg["path"])
    visible: list[CommitSummary] = []
    for c in commits:
        if indexer.filter.should_include_commit(c.files, c.message, c.author):
            visible.append(_commit_to_summary(c))
    logger.info("===>commits: {}", len(visible))
    return visible


@router.get("/projects/{name}/commits/{rev}", response_model=CommitDetail)
async def get_commit_detail(name: str, rev: str, registry = Depends(get_model_registry)):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")
    monitor = create_monitor(cfg["path"])
    commit = await monitor.get_commit(rev)
    ws = get_or_create_session(WikiSessionOptions(project_path=cfg["path"]), registry)
    result = await ws.sync_from_commit(
        changed_files=commit.files, commit_message=commit.message,
        diff=commit.diff, dry_run=True, author=commit.author,
    )

    # Build filtered diff — exclude files blocked by path filters
    indexer = WikiIndexer(cfg["path"])
    filtered_files = indexer.filter.filter_files(commit.files)
    diff_parts: list[str] = []
    for f in filtered_files:
        part = await monitor.get_file_diff(rev, f)
        if part:
            diff_parts.append(part)
    filtered_diff = "\n".join(diff_parts)

    return _commit_to_detail(commit, result.affected, filtered_diff)
