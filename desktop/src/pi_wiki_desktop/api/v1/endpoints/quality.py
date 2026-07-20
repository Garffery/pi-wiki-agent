"""Quality check endpoint."""

from fastapi import APIRouter, HTTPException

from ....config import load_projects
from ....models import QualityIssueItem, QualityReportResponse

router = APIRouter()


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
