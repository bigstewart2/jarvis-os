from pathlib import Path

from core.providers.tts.base import TTSProvider


class ConformingTTSProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def synthesize(self, text: str, output_path: Path) -> None:
        self.calls.append((text, output_path))


def test_conforming_class_satisfies_protocol():
    provider: TTSProvider = ConformingTTSProvider()
    provider.synthesize("hello", Path("out.wav"))
    assert provider.calls == [("hello", Path("out.wav"))]


def test_isinstance_check_against_protocol():
    provider = ConformingTTSProvider()
    assert isinstance(provider, TTSProvider)
