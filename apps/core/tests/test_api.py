from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import SkillInvocation


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_list_skills_includes_echo(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/skills")
    assert response.status_code == 200
    ids = [skill["id"] for skill in response.json()]
    assert "echo" in ids


def test_invoke_echo_skill_returns_outputs(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/skills/echo/invoke", json={"inputs": {"text": "hi"}})
    assert response.status_code == 200
    assert response.json() == {"outputs": {"text": "hi"}}


def test_invoke_echo_skill_logs_to_db(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    client.post("/skills/echo/invoke", json={"inputs": {"text": "logged"}})

    with app.state.session_factory() as session:
        row = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert row.inputs == {"text": "logged"}
        assert row.outputs == {"text": "logged"}
        assert row.status == "completed"


def test_invoke_unknown_skill_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/skills/does-not-exist/invoke", json={"inputs": {}})
    assert response.status_code == 404
