"""Quality check and fix endpoints."""

import asyncio
import json
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from ....config import load_projects
from ....models import QualityIssueItem, QualityReportResponse
from ....sessions.factory import get_model_registry

router = APIRouter()


class QualityFixRequest(BaseModel):
    model: str | None = None
    keep_checkpoint: bool = False


@router.post("/projects/{name}/quality-check", response_model=QualityReportResponse)
async def run_quality_check(name: str):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    from pi_wiki_agent.core.wiki_quality import WikiQualityChecker
    checker = WikiQualityChecker(cfg["path"])
    report = checker.run_checks()

    model_issues = [
        QualityIssueItem(page=i.page, section=i.section, category=i.category,
                         severity=i.severity, check=i.check, message=i.message, detail=i.detail)
        for i in report.issues
    ]
    return QualityReportResponse(
        project_path=report.project_path, checked_at=report.checked_at,
        total_pages=report.total_pages, total_issues=report.total_issues,
        errors=report.errors, warnings=report.warnings, issues=model_issues,
    )


@router.post("/projects/{name}/quality-fix/stream")
async def quality_fix_stream(
    name: str,
    body: QualityFixRequest | None = None,
    registry=Depends(get_model_registry),
):
    """Execute quality fix workflow via SSE streaming."""
    logger.info("==========> quality-fix stream ==================")

    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    # Run quality check first
    from pi_wiki_agent.core.wiki_quality import WikiQualityChecker
    checker = WikiQualityChecker(cfg["path"])
    report = checker.run_checks()

    if report.total_issues == 0:
        async def _no_issues():
            yield f"data: {json.dumps({'type': 'quality_fix_done', 'success': True, 'message': 'No issues found', 'total_issues': 0})}\n\n"
        return StreamingResponse(_no_issues(), media_type="text/event-stream")

    # Load and compile fix_quality workflow script
    import pi_wiki_agent.core.workflow.scripts as _scripts
    from pathlib import Path
    from pi_wiki_agent.core.workflow.ast_compiler import compile_workflow_yaml
    script_path = Path(_scripts.__file__).parent / "fix_quality.yaml"
    yaml_text = script_path.read_text(encoding="utf-8")
    script = compile_workflow_yaml(yaml_text)

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_agent_start(data: dict):
        queue.put_nowait({"type": "workflow_agent_start", "label": data.get("label", ""), "phase": data.get("phase", "")})

    def on_agent_end(data: dict):
        queue.put_nowait({"type": "workflow_agent_end", "label": data.get("label", ""), "phase": data.get("phase", ""), "error": data.get("error")})

    def on_phase(title: str):
        queue.put_nowait({"type": "workflow_phase", "phase": title})

    def on_event(evt: dict):
        queue.put_nowait(evt)

    async def _run():
        from pi_wiki_agent.core.workflow import WorkflowAgent, WorkflowRunOptions, run_workflow
        from pi_coding_agent.core.auth_storage import AuthStorage
        from pi_wiki_agent.core.workflow_sync import _load_workflow_agent_defs, _resolve_model

        try:
            # Load agent defs and resolve model (reuse helpers from workflow_sync)
            agent_defs = _load_workflow_agent_defs(cfg["path"])
            resolved_model = _resolve_model(body.model if body else None, registry)

            agent = WorkflowAgent(
                cwd=cfg["path"],
                model=resolved_model,
                model_registry=registry,
                auth_storage=AuthStorage(),
            )

            result = await run_workflow(
                script,
                WorkflowRunOptions(
                    args={
                        "project_path": cfg["path"],
                        "agent_defs": agent_defs,
                        "commit_hash": "quality-fix",
                        "keep_checkpoint": body.keep_checkpoint if body else False,
                        "quality_report": {
                            "project_path": report.project_path,
                            "checked_at": report.checked_at,
                            "total_pages": report.total_pages,
                            "total_issues": report.total_issues,
                            "errors": report.errors,
                            "warnings": report.warnings,
                            "issues": [
                                {"page": i.page, "section": i.section, "category": i.category,
                                 "severity": i.severity, "check": i.check, "message": i.message}
                                for i in report.issues
                            ],
                        },
                    },
                    cwd=cfg["path"],
                    agent=agent,
                    concurrency=8,
                    on_agent_start=on_agent_start,
                    on_agent_end=on_agent_end,
                    on_phase=on_phase,
                    on_event=on_event,
                ),
            )
            await queue.put({
                "type": "quality_fix_done",
                "success": True,
                "phases": result.phases,
                "agent_count": result.agent_count,
                "duration_ms": result.duration_ms,
                "result": result.result,
            })
        except Exception as exc:
            logger.error("Quality fix failed: {}\n{}", exc, traceback.format_exc())
            await queue.put({"type": "quality_fix_done", "success": False, "error": str(exc)})

    task = asyncio.create_task(_run())

    async def _event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") == "quality_fix_done":
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
