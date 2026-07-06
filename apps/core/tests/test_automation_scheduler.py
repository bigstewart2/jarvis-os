import asyncio
import time
from datetime import datetime, timezone

import pytest
from apscheduler.executors.base import MaxInstancesReachedError

from core.app import create_app
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import AutomationRegistry, LoadedAutomation
from core.automation.runner import AutomationRunner
from core.automation.scheduler import build_scheduler
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill, SkillRegistry


def _valid_definition(automation_id: str, enabled: bool = True) -> AutomationDefinition:
    return AutomationDefinition(
        id=automation_id, name=automation_id, description="test", enabled=enabled,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[StepDefinition(skill="echo", inputs={})],
    )


def test_enabled_valid_automation_gets_a_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=_valid_definition("digest")
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is not None


def test_disabled_automation_gets_no_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=_valid_definition("digest", enabled=False)
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is None


def test_invalid_automation_gets_no_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=None, load_error="bad cron"
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is None


def test_max_instances_one_skips_stacked_run_of_a_slow_automation(tmp_path, monkeypatch):
    # Regression test for the anti-stacking guarantee: a cron firing while
    # the same automation's previous run is still active must be skipped by
    # APScheduler's max_instances=1, not stacked. This requires the job
    # registered with the scheduler to actually await run completion
    # (runner.run_and_wait), rather than fire-and-forget (runner.start).
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    call_count = {"n": 0}

    def slow_skill(inputs):
        call_count["n"] += 1
        time.sleep(0.3)
        return {}

    manifest = SkillManifest(id="slow", name="slow", description="slow skill", input_schema={}, output_schema={})
    app.state.registry._skills["slow"] = LoadedSkill(manifest=manifest, run=slow_skill)

    automation_registry = AutomationRegistry(app.state.registry)
    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[StepDefinition(skill="slow", inputs={})],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    runner = AutomationRunner(automation_registry, app)
    scheduler = build_scheduler(automation_registry, runner)

    async def drive() -> None:
        scheduler.start(paused=True)
        try:
            job = scheduler.get_job("digest")
            executor = scheduler._lookup_executor(job.executor)

            # First "cron fire": submit the job for execution.
            executor.submit_job(job, [datetime.now(timezone.utc)])
            # Give the first run a moment to actually start before the
            # second cron fire arrives while it's still in flight.
            await asyncio.sleep(0.05)

            with pytest.raises(MaxInstancesReachedError):
                executor.submit_job(job, [datetime.now(timezone.utc)])

            # Let the first run finish before tearing down.
            await asyncio.sleep(0.5)
        finally:
            scheduler.shutdown(wait=False)

    asyncio.run(drive())

    assert call_count["n"] == 1
