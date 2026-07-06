import asyncio

from core.app import create_app
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import AutomationRegistry, LoadedAutomation
from core.automation.runner import AutomationRunner
from core.db.models import AutomationRun
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill


def _register_stub_skill(app, skill_id, run_fn):
    manifest = SkillManifest(id=skill_id, name=skill_id, description="stub", input_schema={}, output_schema={})
    app.state.registry._skills[skill_id] = LoadedSkill(manifest=manifest, run=run_fn)


def _make_app_and_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    automation_registry = AutomationRegistry(app.state.registry)
    runner = AutomationRunner(automation_registry, app)
    return app, automation_registry, runner


async def _collect_until(queue, terminal_stages):
    # Filter to automation_run events: the shared event bus also carries
    # skill_invoked events published by invoke_and_record_skill (M4,
    # unchanged) for every step, since a pipeline step is invoked through
    # the exact same path as a button press or voice command.
    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=5.0)
        if event.get("type") != "automation_run":
            continue
        events.append(event)
        if event["stage"] in terminal_stages:
            break
    return events


def test_happy_two_step_run_wires_output_to_input(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    _register_stub_skill(app, "step_one", lambda inputs: {"value": "hello"})
    _register_stub_skill(app, "step_two", lambda inputs: {"received": inputs["text"]})

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={}),
            StepDefinition(skill="step_two", inputs={"text": "{{steps.0.value}}"}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    stages = [e["stage"] for e in events]
    assert stages == ["started", "step_started", "step_completed", "step_started", "step_completed", "completed"]

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "completed"
        assert row.steps == [
            {"skill_id": "step_one", "status": "completed"},
            {"skill_id": "step_two", "status": "completed"},
        ]


def test_step_failure_stops_pipeline_and_records_failed_step(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    calls = []

    def failing_run(inputs):
        raise RuntimeError("boom")

    def step_two_run(inputs):
        calls.append("ran")
        return {"ok": True}

    _register_stub_skill(app, "step_one", failing_run)
    _register_stub_skill(app, "step_two", step_two_run)

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={}),
            StepDefinition(skill="step_two", inputs={}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"
    assert events[-1]["detail"]["failed_step"] == 0
    assert calls == []

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
        assert row.failed_step == 0


def test_render_error_fails_run_before_invoking_skill(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    calls = []

    def step_one_run(inputs):
        calls.append("ran")
        return {"ok": True}

    _register_stub_skill(app, "step_one", step_one_run)

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={"text": "{{steps.5.missing}}"}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"
    assert "render_error" in events[-1]["detail"]["error"]
    assert calls == []

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
        assert row.failed_step == 0


def test_unknown_automation_id_still_writes_terminal_failed_state(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("does-not-exist", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
