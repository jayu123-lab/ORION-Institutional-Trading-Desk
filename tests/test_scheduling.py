"""Tests for scheduling engine."""
import pytest
from datetime import datetime
from core.scheduling.scheduler import SchedulerEngine


@pytest.mark.asyncio
async def test_scheduler_initialization():
    """Test scheduler initialization."""
    scheduler = SchedulerEngine()
    assert not scheduler.is_running()
    
    await scheduler.start()
    assert scheduler.is_running()
    
    await scheduler.stop()
    assert not scheduler.is_running()


@pytest.mark.asyncio
async def test_add_interval_job():
    """Test adding interval-based job."""
    scheduler = SchedulerEngine()
    await scheduler.start()
    
    counter = {"calls": 0}
    
    def increment():
        counter["calls"] += 1
    
    scheduler.add_interval_job(
        increment,
        minutes=1,
        job_id="test_interval",
    )
    
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "test_interval"
    
    await scheduler.stop()


@pytest.mark.asyncio
async def test_add_cron_job():
    """Test adding cron-based job."""
    scheduler = SchedulerEngine()
    await scheduler.start()
    
    def test_func():
        pass
    
    scheduler.add_cron_job(
        test_func,
        "0 * * * *",
        "test_cron",
    )
    
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "test_cron"
    
    await scheduler.stop()


@pytest.mark.asyncio
async def test_remove_job():
    """Test removing a job."""
    scheduler = SchedulerEngine()
    await scheduler.start()
    
    def dummy():
        pass
    
    scheduler.add_interval_job(dummy, minutes=5, job_id="removable")
    assert len(scheduler.get_jobs()) == 1
    
    scheduler.remove_job("removable")
    assert len(scheduler.get_jobs()) == 0
    
    await scheduler.stop()
