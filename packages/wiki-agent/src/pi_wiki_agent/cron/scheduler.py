"""
Singleton async scheduler using APScheduler.
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from pi_wiki_agent.logging import logger


class CronScheduler:
    """Wrapper around APScheduler AsyncIOScheduler for wiki-agent tasks."""

    def __init__(self):
        jobstores = {"default": MemoryJobStore()}
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone="Asia/Shanghai",
        )
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    def start(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("[cron] scheduler started")

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("[cron] scheduler shutdown")

    def add_cron_job(
        self,
        func,
        *,
        job_id: str,
        name: str = "",
        minute: str = "0",
        hour: str = "0",
        day: str = "*",
        month: str = "*",
        day_of_week: str = "*",
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> str:
        """Add a cron-triggered job.

        Args:
            func: async callable to execute.
            job_id: unique identifier (used for update/remove).
            name: human-readable description.
            minute, hour, day, month, day_of_week: standard cron fields.
            args: positional arguments to pass to func.
            kwargs: keyword arguments to pass to func.
        Returns:
            job_id.
        """
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day,
            month=month, day_of_week=day_of_week,
            timezone="Asia/Shanghai",
        )
        self._scheduler.add_job(
            func, trigger=trigger, id=job_id, name=name or job_id,
            args=args, kwargs=kwargs, replace_existing=True,
        )
        logger.info("[cron] job added: id={} name={} cron={} {} {} {} {} args={} kwargs={}",
                     job_id, name or job_id, minute, hour, day, month, day_of_week, args, kwargs)
        return job_id

    def add_interval_job(
        self,
        func,
        *,
        job_id: str,
        name: str = "",
        minutes: int = 30,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> str:
        """Add an interval-triggered job (runs every N minutes)."""
        trigger = IntervalTrigger(minutes=minutes, timezone="Asia/Shanghai")
        self._scheduler.add_job(
            func, trigger=trigger, id=job_id, name=name or job_id,
            args=args, kwargs=kwargs, replace_existing=True,
        )
        logger.info("[cron] job added: id={} name={} interval={}min args={} kwargs={}",
                     job_id, name or job_id, minutes, args, kwargs)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        try:
            self._scheduler.remove_job(job_id)
            logger.info("[cron] job removed: id={}", job_id)
            return True
        except Exception:
            return False

    def list_jobs(self) -> list[dict]:
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": j.id,
                "name": j.name,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
            }
            for j in jobs
        ]

    def pause_job(self, job_id: str) -> bool:
        try:
            self._scheduler.pause_job(job_id)
            logger.info("[cron] job paused: id={}", job_id)
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        try:
            self._scheduler.resume_job(job_id)
            logger.info("[cron] job resumed: id={}", job_id)
            return True
        except Exception:
            return False


# Singleton
scheduler = CronScheduler()
