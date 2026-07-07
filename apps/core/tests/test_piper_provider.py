import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import PiperProvider, PiperTTSError

PIPER_BIN = str(Path(sys.executable).parent / "piper")


def _settings(voices_dir: Path) -> Settings:
    return Settings(
        anthropic_api_key=None,
        piper_voice="en_US-lessac-medium",
        piper_voices_dir=str(voices_dir),
    )


def _create_fake_model(voices_dir: Path) -> Path:
    voices_dir.mkdir(parents=True, exist_ok=True)
    model_path = voices_dir / "en_US-lessac-medium.onnx"
    model_path.write_bytes(b"fake-onnx-bytes")
    return model_path


def test_synthesize_calls_piper_with_correct_args(monkeypatch, tmp_path):
    model_path = _create_fake_model(tmp_path / "voices")
    captured = {}

    def fake_run(args, input, text, capture_output):
        captured["args"] = args
        captured["input"] = input
        return Mock(returncode=0, stderr="")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings(tmp_path / "voices"))
    output_path = tmp_path / "out.wav"

    provider.synthesize("hello world", output_path)

    assert captured["args"] == [
        PIPER_BIN,
        "--model",
        str(model_path),
        "--output_file",
        str(output_path),
    ]
    assert captured["input"] == "hello world"


def test_synthesize_raises_on_nonzero_exit(monkeypatch, tmp_path):
    _create_fake_model(tmp_path / "voices")

    def fake_run(args, input, text, capture_output):
        return Mock(returncode=1, stderr="model not found")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings(tmp_path / "voices"))

    with pytest.raises(PiperTTSError, match="model not found"):
        provider.synthesize("hello", tmp_path / "out.wav")


def test_synthesize_raises_with_download_hint_when_model_missing(tmp_path):
    provider = PiperProvider(_settings(tmp_path / "voices"))

    with pytest.raises(PiperTTSError, match="piper.download_voices en_US-lessac-medium"):
        provider.synthesize("hello", tmp_path / "out.wav")
