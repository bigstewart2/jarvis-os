from pathlib import Path

from core.providers.stt.base import STTProvider


class ConformingSTTProvider:
    def transcribe(self, audio_path: Path) -> str:
        return f"transcribed:{audio_path.name}"


def test_conforming_class_satisfies_protocol():
    provider: STTProvider = ConformingSTTProvider()
    assert provider.transcribe(Path("clip.wav")) == "transcribed:clip.wav"


def test_isinstance_check_against_protocol():
    provider = ConformingSTTProvider()
    assert isinstance(provider, STTProvider)
