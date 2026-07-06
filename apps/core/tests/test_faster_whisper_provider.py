from pathlib import Path

from core.config import Settings
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    construct_count = 0

    def __init__(self, model_name: str, compute_type: str) -> None:
        FakeWhisperModel.construct_count += 1
        self.model_name = model_name
        self.compute_type = compute_type

    def transcribe(self, path: str):
        return [FakeSegment(" hello "), FakeSegment("world ")], {"language": "en"}


def _settings() -> Settings:
    return Settings(anthropic_api_key=None, stt_model="small", stt_compute_type="int8")


def test_transcribe_joins_and_strips_segments(monkeypatch):
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    result = provider.transcribe(Path("clip.wav"))

    assert result == "hello world"


def test_constructs_model_with_configured_args(monkeypatch):
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    provider.transcribe(Path("clip.wav"))

    assert provider._model.model_name == "small"
    assert provider._model.compute_type == "int8"


def test_loads_model_lazily_only_once(monkeypatch):
    FakeWhisperModel.construct_count = 0
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    assert FakeWhisperModel.construct_count == 0

    provider.transcribe(Path("clip1.wav"))
    provider.transcribe(Path("clip2.wav"))

    assert FakeWhisperModel.construct_count == 1
