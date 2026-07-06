from fastapi.testclient import TestClient

from core.app import create_app
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import AutomationRun


def test_startup_marks_stale_running_automation_runs_as_interrupted(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("JARVIS_DATABASE_URL", db_url)

    engine = make_engine(db_url)
    init_db(engine)
    seed_session_factory = make_session_factory(engine)
    with seed_session_factory() as session:
        session.add(
            AutomationRun(run_id="stale-1", automation_id="digest", trigger="cron", status="running", steps=[])
        )
        session.commit()

    app = create_app()
    with TestClient(app):
        with app.state.session_factory() as session:
            row = session.get(AutomationRun, "stale-1")
            assert row.status == "interrupted"


def test_app_state_has_automation_components(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    assert app.state.automation_registry is not None
    assert app.state.automation_runner is not None
    assert app.state.scheduler is not None
