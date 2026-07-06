from fastapi.testclient import TestClient

from core.app import create_app
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import ClaudeCodeTask


def test_startup_marks_stale_running_tasks_as_interrupted(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("JARVIS_DATABASE_URL", db_url)

    engine = make_engine(db_url)
    init_db(engine)
    seed_session_factory = make_session_factory(engine)
    with seed_session_factory() as session:
        session.add(
            ClaudeCodeTask(task_id="stale-1", prompt="x", working_dir="/tmp", status="running")
        )
        session.commit()

    app = create_app()
    with TestClient(app):
        with app.state.session_factory() as session:
            row = session.get(ClaudeCodeTask, "stale-1")
            assert row.status == "interrupted"


def test_app_state_has_task_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    assert app.state.task_manager is not None
