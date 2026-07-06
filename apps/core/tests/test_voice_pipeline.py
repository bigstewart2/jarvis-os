import asyncio

from core.app import create_app
from core.db.models import RouteDecision
from core.skills.registry import LoadedSkill
from core.voice.pipeline import run_voice_pipeline


class FakeSTT:
    def __init__(self, transcript: str = "what is two plus two", raise_exc: Exception | None = None):
        self.transcript = transcript
        self.raise_exc = raise_exc

    def transcribe(self, audio_path):
        if self.raise_exc:
            raise self.raise_exc
        return self.transcript


class FakeTTS:
    def __init__(self, raise_exc: Exception | None = None):
        self.raise_exc = raise_exc
        self.calls: list[str] = []

    def synthesize(self, text, output_path):
        self.calls.append(text)
        if self.raise_exc:
            raise self.raise_exc
        output_path.write_bytes(b"RIFF-fake-wav-bytes")


class FakeRouterLLM:
    def __init__(self, response: str):
        self.response = response

    def complete(self, prompt, *, system=None):
        return self.response


class RaisingLLM:
    def complete(self, prompt, *, system=None):
        raise RuntimeError("provider down")


def _make_app(
    tmp_path,
    monkeypatch,
    stt=None,
    tts=None,
    llm_response='{"skill_id": "echo", "inputs": {"text": "hi"}}',
):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice"))
    app = create_app()
    app.state.stt_provider = stt or FakeSTT()
    app.state.tts_provider = tts or FakeTTS()
    monkeypatch.setattr(
        "core.voice.pipeline.get_llm_provider", lambda settings: FakeRouterLLM(llm_response)
    )
    return app


def test_happy_path_invokes_skill_and_returns_full_result(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["transcript"] == "what is two plus two"
    assert result["skill_id"] == "echo"
    assert result["fallback_used"] is False
    assert result["outputs"] == {"text": "hi"}
    assert result["response_text"] == "hi"
    assert result["error"] is None
    assert result["audio_url"] is not None


def test_empty_transcript_skips_routing_and_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, stt=FakeSTT(transcript="   "))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["transcript"] == ""
    assert result["skill_id"] is None
    assert result["error"] == "empty_transcript"
    assert result["response_text"] == "I didn't catch that."


def test_stt_failure_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, stt=FakeSTT(raise_exc=RuntimeError("bad audio")))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "I couldn't process that audio."
    assert "stt_failed" in result["error"]


def test_llm_failure_during_routing_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    monkeypatch.setattr("core.voice.pipeline.get_llm_provider", lambda settings: RaisingLLM())

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "I couldn't reach the language model."
    assert "routing_failed" in result["error"]


def test_skill_failure_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    original = app.state.registry.get("echo")

    def failing_run(inputs):
        raise RuntimeError("echo blew up")

    app.state.registry._skills["echo"] = LoadedSkill(manifest=original.manifest, run=failing_run)

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "The echo skill failed."
    assert "skill_failed" in result["error"]


def test_tts_failure_still_returns_full_result_without_audio(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, tts=FakeTTS(raise_exc=RuntimeError("piper missing")))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["skill_id"] == "echo"
    assert result["outputs"] == {"text": "hi"}
    assert result["audio_url"] is None
    assert "tts_failed" in result["error"]


def test_fallback_route_invokes_ask_and_logs_route_decision(tmp_path, monkeypatch):
    app = _make_app(
        tmp_path,
        monkeypatch,
        llm_response='{"skill_id": "ask", "inputs": {"prompt": "what is two plus two"}}',
    )
    # The ask skill's own run() imports get_llm_provider independently (it's a
    # dynamically-loaded skill module, not core.voice.pipeline) — monkeypatching
    # core.voice.pipeline.get_llm_provider only fakes the ROUTER's LLM call, not
    # ask's own answer-generation call. Fake that separately via __globals__,
    # same technique used in Milestone 3's test_ask_skill.py.
    ask_loaded = app.state.registry.get("ask")
    monkeypatch.setitem(ask_loaded.run.__globals__, "get_llm_provider", lambda settings: FakeRouterLLM("4"))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["skill_id"] == "ask"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "model_chose_ask"
    assert result["outputs"] == {"response": "4"}

    with app.state.session_factory() as session:
        rows = session.query(RouteDecision).all()
        assert len(rows) == 1
        assert rows[0].fallback_used is True
        assert rows[0].fallback_reason == "model_chose_ask"
