"""
Predefined scheduled jobs for wiki-agent.
"""
from __future__ import annotations

from pi_wiki_agent.logging import logger


async def _auto_pick_model():
    """Pick the first available model from the registry. Returns None if none found."""
    try:
        from pi_coding_agent.core.model_registry import ModelRegistry
        from pi_coding_agent.core.auth_storage import AuthStorage
        registry = ModelRegistry(auth_storage=AuthStorage())
        models = await registry.get_available()
        if models:
            logger.info("[cron] auto-picked model: {}/{}", models[0].provider, models[0].id)
            return models[0]
    except Exception:
        logger.warning("[cron] failed to auto-pick model")
    return None


async def quality_check_job(project_path: str) -> dict:
    """Run quality check on a project. If issues found, auto-trigger fix workflow."""
    from pi_wiki_agent.core.wiki_quality import WikiQualityChecker

    logger.info("[cron:quality-check] running for {}", project_path)
    checker = WikiQualityChecker(project_path)
    report = checker.run_checks()

    result = {
        "project_path": project_path,
        "total_pages": report.total_pages,
        "total_issues": report.total_issues,
        "errors": report.errors,
        "warnings": report.warnings,
    }

    if report.total_issues > 0:
        logger.info("[cron:quality-check] {} issues found, auto-triggering fix workflow", report.total_issues)
        fix_result = await quality_fix_job(project_path)
        result["fix_triggered"] = True
        result["fix_result"] = fix_result
    else:
        logger.info("[cron:quality-check] no issues found")
        result["fix_triggered"] = False

    return result


async def vcs_poll_job(project_path: str) -> dict | None:
    """Poll VCS for new commits. Returns the latest commit if unprocessed, else None."""
    from pi_wiki_agent.vcs import create_monitor

    logger.info("[cron:vcs-poll] polling {}", project_path)
    monitor = create_monitor(project_path)
    commits = await monitor.poll()

    if not commits:
        logger.info("[cron:vcs-poll] no new commits")
        return None

    latest = commits[-1]
    logger.info("[cron:vcs-poll] new commit: {} {}", latest.revision[:8], latest.message[:80])
    return {
        "project_path": project_path,
        "revision": latest.revision,
        "message": latest.message,
        "files": latest.files,
        "diff": latest.diff,
    }


async def quality_fix_job(project_path: str, model: str | None = None) -> dict:
    """Run quality fix workflow on a project. Returns the result summary.

    If model is None, auto-resolves from the built-in model registry.
    """
    from pi_wiki_agent.core.wiki_quality import WikiQualityChecker
    from pi_wiki_agent.core.workflow import WorkflowAgent, WorkflowRunOptions, run_workflow
    from pi_wiki_agent.core.workflow_sync import _load_workflow_agent_defs
    from pathlib import Path
    import os

    logger.info("[cron:quality-fix] running for {}", project_path)

    # Auto-resolve model if not specified
    resolved_model = None
    if model:
        from pi_coding_agent.core.model_registry import ModelRegistry
        from pi_coding_agent.core.auth_storage import AuthStorage
        registry = ModelRegistry(auth_storage=AuthStorage())
        try:
            provider, model_id = model.split(":", 1)
            resolved_model = registry.resolve_model(model_id=model_id, provider=provider)
        except Exception:
            pass
    if resolved_model is None:
        resolved_model = await _auto_pick_model()
    if resolved_model:
        logger.info("[cron:quality-fix] using model: {}/{}",
                    resolved_model.provider, resolved_model.id)

    # Check if there are issues first
    checker = WikiQualityChecker(project_path)
    report = checker.run_checks()
    if report.total_issues == 0:
        logger.info("[cron:quality-fix] no issues, skipping")
        return {"project_path": project_path, "fixed": 0, "message": "No issues found"}

    # Load and compile workflow script
    import pi_wiki_agent.core.workflow.scripts as _scripts
    from pi_wiki_agent.core.workflow.ast_compiler import compile_workflow_yaml
    script_path = Path(_scripts.__file__).parent / "fix_quality.yaml"
    yaml_text = script_path.read_text(encoding="utf-8")
    script = compile_workflow_yaml(yaml_text)

    agent_defs = _load_workflow_agent_defs(project_path)
    agent = WorkflowAgent(cwd=project_path, model=resolved_model)

    # Generate a safe namespace (Windows doesn't allow : in paths)
    safe_ts = report.checked_at.replace(":", "-").replace("T", "-").replace("+", "-")
    namespace = f"cron-fix-{safe_ts}"

    result = await run_workflow(
        script,
        WorkflowRunOptions(
            args={
                "project_path": project_path,
                "agent_defs": agent_defs,
                "commit_hash": namespace,
                "quality_report": {
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
            cwd=project_path,
            agent=agent,
            concurrency=8,
        ),
    )

    fix_phase = result.result.get("phase3_fix", {})
    logger.info("[cron:quality-fix] done: {} tasks, {} succeeded, {} failed",
                fix_phase.get("total_tasks", 0), fix_phase.get("succeeded", 0), fix_phase.get("failed", 0))

    # Log details on failure
    if fix_phase.get("failed", 0) > 0 or fix_phase.get("total_tasks", 0) == 0:
        error_msg = fix_phase.get("error", "unknown")
        logger.error("[cron:quality-fix] FAILED: error={}, plan_phase={}, workflow_logs:",
                     error_msg, result.result.get("phase2_plan") is not None)
        for line in result.logs[-20:]:  # last 20 log lines
            logger.error("[cron:quality-fix]   {}", line)

    return {
        "project_path": project_path,
        "total_tasks": fix_phase.get("total_tasks", 0),
        "succeeded": fix_phase.get("succeeded", 0),
        "failed": fix_phase.get("failed", 0),
    }
