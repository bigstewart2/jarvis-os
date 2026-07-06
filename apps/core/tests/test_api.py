import threading
import time

from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import SkillInvocation
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill


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


def test_websocket_receives_skill_invoked_event(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    with client.websocket_connect("/ws") as websocket:
        client.post("/skills/echo/invoke", json={"inputs": {"text": "streamed"}})
        event = websocket.receive_json()

    assert event["type"] == "skill_invoked"
    assert event["skill_id"] == "echo"
    assert event["status"] == "completed"
    assert event["outputs"] == {"text": "streamed"}


def test_cors_allows_tauri_dev_origin(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/skills", headers={"Origin": "http://localhost:1420"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:1420"


def test_slow_skill_invocation_does_not_block_other_requests(tmp_path, monkeypatch):
    """A blocking skill.run() must not stall the event loop for other requests.

    Registers a fake skill whose run() sleeps for 0.5s (simulating a slow LLM
    completion), fires that invocation on a background thread, and — while it
    is still in flight — issues a fast /skills/echo/invoke request on the main
    thread. Before the run_in_threadpool fix, `loaded.run` was awaited inline
    on the single event loop, so the synchronous time.sleep(0.5) would block
    ALL requests (including this concurrent echo call) for the full 0.5s.
    After the fix, the slow run() executes in FastAPI's threadpool, so the
    echo request should complete quickly regardless of the slow skill still
    running.
    """
    client, app = _client(tmp_path, monkeypatch)

    def slow_run(inputs: dict) -> dict:
        time.sleep(0.5)
        return {"text": inputs.get("text", "")}

    app.state.registry._skills["slow"] = LoadedSkill(
        manifest=SkillManifest(id="slow", name="Slow", description="Blocks briefly"),
        run=slow_run,
    )

    results = {}

    def invoke_slow_skill():
        response = client.post("/skills/slow/invoke", json={"inputs": {"text": "slow"}})
        results["slow_status"] = response.status_code

    # Plain (non-context-manager) TestClient.post() calls each spin up their
    # own throwaway event loop, which would trivially "pass" this test for
    # the wrong reason (no shared loop to block). Using `with client:` makes
    # every request in this block share a single portal/event loop — the
    # same way a real running server shares one event loop across requests —
    # so a synchronous, un-threadpooled `loaded.run` would actually starve it.
    with client:
        thread = threading.Thread(target=invoke_slow_skill)
        thread.start()
        time.sleep(0.1)  # give the slow invocation time to actually start running

        start = time.monotonic()
        echo_response = client.post("/skills/echo/invoke", json={"inputs": {"text": "fast"}})
        echo_elapsed = time.monotonic() - start

        thread.join()

    assert echo_response.status_code == 200
    assert echo_response.json() == {"outputs": {"text": "fast"}}
    assert results["slow_status"] == 200
    # The echo call should return almost immediately. If the event loop were
    # still blocked by the slow skill's inline synchronous sleep, this would
    # take close to the remaining ~0.4s of that sleep instead.
    assert echo_elapsed < 0.3


def test_app_state_has_stt_and_tts_providers(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert app.state.stt_provider is not None
    assert app.state.tts_provider is not None
