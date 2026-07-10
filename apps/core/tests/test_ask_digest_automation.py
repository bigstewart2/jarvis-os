from core.app import create_app


def test_ask_digest_automation_loads_as_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    loaded = app.state.automation_registry.get("ask_digest")

    assert loaded is not None
    assert loaded.is_valid, loaded.load_error
    assert loaded.definition.steps[0].skill == "ask"
    assert loaded.definition.steps[1].skill == "speak"


def test_ask_digest_automation_is_disabled_and_not_scheduled(tmp_path, monkeypatch):
    # ask_digest was the placeholder morning automation; morning_brief replaced it.
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    loaded = app.state.automation_registry.get("ask_digest")
    assert loaded is not None
    assert loaded.definition.enabled is False
    assert app.state.scheduler.get_job("ask_digest") is None


def test_morning_brief_automation_loads_and_gets_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    loaded = app.state.automation_registry.get("morning_brief")

    assert loaded is not None
    assert loaded.is_valid, loaded.load_error
    assert loaded.definition.steps[0].skill == "daily_brief"
    assert loaded.definition.steps[1].skill == "speak"
    assert app.state.scheduler.get_job("morning_brief") is not None
