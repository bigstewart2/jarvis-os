from datetime import datetime, timezone

from fastapi.testclient import TestClient

from core.app import create_app
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import LoadedAutomation
from core.db.models import AutomationRun
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def _register_stub_skill(app, skill_id="echo"):
    manifest = SkillManifest(id=skill_id, name=skill_id, description="stub", input_schema={}, output_schema={})
    app.state.registry._skills[skill_id] = LoadedSkill(manifest=manifest, run=lambda inputs: {"text": "hi"})


def _register_automation(app, automation_id="digest", enabled=True):
    definition = AutomationDefinition(
        id=automation_id, name="Digest", description="test", enabled=enabled,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[StepDefinition(skill="echo", inputs={})],
    )
    app.state.automation_registry._automations[automation_id] = LoadedAutomation(
        automation_id=automation_id, definition=definition
    )


def test_list_automations_includes_registered_automation(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_automation(app)

    response = client.get("/automations")

    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert "digest" in ids


def test_list_automations_surfaces_invalid_load_error(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    app.state.automation_registry._automations["bad"] = LoadedAutomation(
        automation_id="bad", definition=None, load_error="bad cron"
    )

    response = client.get("/automations")

    entry = next(a for a in response.json() if a["id"] == "bad")
    assert entry["status"] == "invalid"
    assert entry["load_error"] == "bad cron"


def test_trigger_automation_returns_202_with_run_id(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_stub_skill(app)
    _register_automation(app)

    response = client.post("/automations/digest/run")

    assert response.status_code == 202
    assert "run_id" in response.json()


def test_trigger_unknown_automation_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post("/automations/does-not-exist/run")

    assert response.status_code == 404


def test_trigger_invalid_automation_returns_409(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    app.state.automation_registry._automations["bad"] = LoadedAutomation(
        automation_id="bad", definition=None, load_error="bad cron"
    )

    response = client.post("/automations/bad/run")

    assert response.status_code == 409


def test_trigger_disabled_automation_still_works(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_stub_skill(app)
    _register_automation(app, enabled=False)

    response = client.post("/automations/digest/run")

    assert response.status_code == 202


def test_list_automation_runs_returns_newest_first(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(AutomationRun(
            run_id="first", automation_id="digest", trigger="cron", status="completed", steps=[],
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        session.add(AutomationRun(
            run_id="second", automation_id="digest", trigger="cron", status="completed", steps=[],
            started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ))
        session.commit()

    response = client.get("/automations/runs")

    assert [r["run_id"] for r in response.json()] == ["second", "first"]


def test_get_automation_run_returns_404_for_unknown_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/automations/runs/does-not-exist")

    assert response.status_code == 404


def test_get_automation_run_returns_full_record(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(AutomationRun(
            run_id="abc", automation_id="digest", trigger="manual", status="failed",
            steps=[{"skill_id": "echo", "status": "failed", "error": "boom"}],
            failed_step=0, error="boom",
        ))
        session.commit()

    response = client.get("/automations/runs/abc")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_step"] == 0
    assert body["steps"] == [{"skill_id": "echo", "status": "failed", "error": "boom"}]
