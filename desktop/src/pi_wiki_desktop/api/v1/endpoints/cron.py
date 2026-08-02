"""Cron job management API."""

from fastapi import APIRouter
from pydantic import BaseModel

from pi_wiki_agent.cron import scheduler

router = APIRouter()


class CronJobRequest(BaseModel):
    job_id: str
    name: str = ""
    minute: str = "0"
    hour: str = "0"
    day: str = "*"
    month: str = "*"
    day_of_week: str = "*"
    task: str  # "quality_check" or "vcs_poll"
    project_path: str = ""  # target project path


@router.get("/cron/jobs")
def list_jobs():
    """List all registered scheduled jobs."""
    return {"jobs": scheduler.list_jobs()}


@router.post("/cron/jobs")
def add_cron_job(req: CronJobRequest):
    """Add a cron-triggered job."""
    from pi_wiki_agent.cron.jobs import quality_check_job, vcs_poll_job

    task_map = {
        "quality_check": quality_check_job,
        "vcs_poll": vcs_poll_job,
    }
    func = task_map.get(req.task)
    if func is None:
        return {"error": f"Unknown task: {req.task}. Available: {list(task_map.keys())}"}

    kwargs = {}
    if req.project_path:
        kwargs["project_path"] = req.project_path

    job_id = scheduler.add_cron_job(
        func, job_id=req.job_id, name=req.name,
        minute=req.minute, hour=req.hour, day=req.day,
        month=req.month, day_of_week=req.day_of_week,
        kwargs=kwargs,
    )
    return {"added": job_id}


@router.delete("/cron/jobs/{job_id}")
def remove_job(job_id: str):
    """Remove a scheduled job."""
    ok = scheduler.remove_job(job_id)
    return {"removed": ok}


@router.post("/cron/jobs/{job_id}/pause")
def pause_job(job_id: str):
    ok = scheduler.pause_job(job_id)
    return {"paused": ok}


@router.post("/cron/jobs/{job_id}/resume")
def resume_job(job_id: str):
    ok = scheduler.resume_job(job_id)
    return {"resumed": ok}
