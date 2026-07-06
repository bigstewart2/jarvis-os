from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import AutomationRegistry, LoadedAutomation
from core.automation.runner import AutomationRunner
from core.automation.scheduler import build_scheduler
from core.skills.registry import SkillRegistry


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
