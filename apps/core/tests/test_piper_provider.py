from unittest.mock import Mock

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import PiperProvider, PiperTTSError


def _settings() -> Settings:
    return Settings(anthropic_api_key=None, piper_voice="en_US-lessac-medium")


def test_synthesize_calls_piper_with_correct_args(monkeypatch, tmp_path):
    captured = {}

    def fake_run(args, input, text, capture_output):
        captured["args"] = args
        captured["input"] = input
        return Mock(returncode=0, stderr="")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings())
    output_path = tmp_path / "out.wav"

    provider.synthesize("hello world", output_path)

    assert captured["args"] == [
        "piper",
        "--model",
        "en_US-lessac-medium",
        "--output_file",
        str(output_path),
    ]
    assert captured["input"] == "hello world"


def test_synthesize_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(args, input, text, capture_output):
        return Mock(returncode=1, stderr="model not found")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings())

    with pytest.raises(PiperTTSError, match="model not found"):
        provider.synthesize("hello", tmp_path / "out.wav")
