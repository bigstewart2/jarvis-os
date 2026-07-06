from core.app import create_app


def test_ask_digest_automation_loads_as_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    loaded = app.state.automation_registry.get("ask_digest")

    assert loaded is not None
    assert loaded.is_valid, loaded.load_error
    assert loaded.definition.steps[0].skill == "ask"
    assert loaded.definition.steps[1].skill == "speak"


def test_ask_digest_automation_gets_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    assert app.state.scheduler.get_job("ask_digest") is not None
