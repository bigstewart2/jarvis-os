from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.automation.registry import AutomationRegistry
from core.automation.runner import AutomationRunner


def build_scheduler(automation_registry: AutomationRegistry, runner: AutomationRunner) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for loaded in automation_registry.list():
        if not loaded.is_valid or not loaded.definition.enabled:
            continue
        scheduler.add_job(
            runner.start,
            trigger=CronTrigger.from_crontab(loaded.definition.trigger.cron),
            args=[loaded.automation_id, "cron"],
            id=loaded.automation_id,
            coalesce=True,
            misfire_grace_time=60,
            max_instances=1,
        )
    return scheduler
