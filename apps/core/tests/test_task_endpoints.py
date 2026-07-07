from datetime import datetime, timezone

from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import ClaudeCodeTask


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_get_task_returns_404_for_unknown_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/tasks/does-not-exist")

    assert response.status_code == 404


def test_get_task_returns_full_record(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(
            ClaudeCodeTask(
                task_id="abc-123", prompt="do X", working_dir="/tmp", status="completed",
                result_text="Done.", num_turns=2, duration_ms=500, cost_usd=0.02,
            )
        )
        session.commit()

    response = client.get("/tasks/abc-123")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "abc-123"
    assert body["status"] == "completed"
    assert body["result_text"] == "Done."
    assert body["num_turns"] == 2
    assert body["cost_usd"] == 0.02


def test_list_tasks_returns_newest_first(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(ClaudeCodeTask(
            task_id="first", prompt="a", working_dir="/tmp", status="completed",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        session.add(ClaudeCodeTask(
            task_id="second", prompt="b", working_dir="/tmp", status="completed",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ))
        session.commit()

    response = client.get("/tasks")

    assert response.status_code == 200
    body = response.json()
    assert [t["task_id"] for t in body] == ["second", "first"]
