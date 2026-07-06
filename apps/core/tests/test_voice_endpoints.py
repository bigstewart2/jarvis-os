import io

from fastapi.testclient import TestClient

from core.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice"))
    app = create_app()
    return TestClient(app), app


class FakeSTT:
    def transcribe(self, audio_path):
        return "say hi to me"


class FakeTTS:
    def synthesize(self, text, output_path):
        output_path.write_bytes(b"RIFF-fake-wav-bytes")


class FakeRouterLLM:
    def complete(self, prompt, *, system=None):
        return '{"skill_id": "echo", "inputs": {"text": "hi"}}'


def _wire_fakes(app, monkeypatch):
    app.state.stt_provider = FakeSTT()
    app.state.tts_provider = FakeTTS()
    monkeypatch.setattr("core.voice.pipeline.get_llm_provider", lambda settings: FakeRouterLLM())


def test_voice_invoke_returns_full_pipeline_result(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _wire_fakes(app, monkeypatch)

    response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b"fake-audio-bytes"), "audio/webm")},
        data={"invocation_id": "test-invocation-id"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "say hi to me"
    assert body["skill_id"] == "echo"
    assert body["audio_url"].startswith("/voice/audio/")
    assert body["invocation_id"] == "test-invocation-id"


def test_voice_invoke_returns_400_for_empty_upload(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b""), "audio/webm")},
        data={"invocation_id": "test-invocation-id"},
    )

    assert response.status_code == 400


def test_get_voice_audio_serves_generated_file(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _wire_fakes(app, monkeypatch)

    invoke_response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b"fake-audio-bytes"), "audio/webm")},
        data={"invocation_id": "test-invocation-id"},
    )
    audio_url = invoke_response.json()["audio_url"]

    audio_response = client.get(audio_url)

    assert audio_response.status_code == 200
    assert audio_response.content == b"RIFF-fake-wav-bytes"


def test_get_voice_audio_rejects_non_uuid_id(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.get("/voice/audio/not-a-uuid")

    assert response.status_code == 400
