from datetime import datetime
from typing import Callable, Optional
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Manages scheduled tasks for market events, data collection, and analyses."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self):
        """Start the scheduler."""
        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("Scheduler stopped")

    def add_cron_job(
        self,
        func: Callable,
        cron_expression: str,
        job_id: str,
        args: tuple = (),
        kwargs: dict = None,
    ):
        """Add a cron-based scheduled job."""
        if kwargs is None:
            kwargs = {}

        try:
            self.scheduler.add_job(
                func,
                trigger=CronTrigger.from_crontab(cron_expression),
                id=job_id,
                args=args,
                kwargs=kwargs,
                replace_existing=True,
            )
            logger.info(f"Added cron job: {job_id} ({cron_expression})")
        except Exception as e:
            logger.error(f"Failed to add cron job {job_id}: {e}")
            raise

    def add_interval_job(
        self,
        func: Callable,
        minutes: int,
        job_id: str,
        args: tuple = (),
        kwargs: dict = None,
    ):
        """Add an interval-based scheduled job."""
        if kwargs is None:
            kwargs = {}

        try:
            self.scheduler.add_job(
                func,
                trigger=IntervalTrigger(minutes=minutes),
                id=job_id,
                args=args,
                kwargs=kwargs,
                replace_existing=True,
            )
            logger.info(f"Added interval job: {job_id} (every {minutes} min)")
        except Exception as e:
            logger.error(f"Failed to add interval job {job_id}: {e}")
            raise

    def remove_job(self, job_id: str):
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")

    def get_jobs(self) -> list:
        """Get all scheduled jobs."""
        return self.scheduler.get_jobs()

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
