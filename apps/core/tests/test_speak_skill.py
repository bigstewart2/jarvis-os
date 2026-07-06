from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def test_manifest_is_not_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("speak")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_run_synthesizes_and_returns_audio_url(monkeypatch, tmp_path):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("speak")

    class FakeSettings:
        voice_dir = str(tmp_path)

    class FakeTTSProvider:
        def synthesize(self, text, output_path):
            output_path.write_bytes(b"RIFF-fake-wav-bytes")

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())
    monkeypatch.setitem(loaded.run.__globals__, "get_tts_provider", lambda settings: FakeTTSProvider())

    result = loaded.run({"text": "hello world"})

    assert result["text"] == "hello world"
    assert result["audio_url"].startswith("/voice/audio/")
