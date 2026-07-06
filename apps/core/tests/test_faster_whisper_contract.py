from pathlib import Path

import pytest

from core.config import Settings
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_speech.wav"


def _faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample_speech.wav fixture not present")
@pytest.mark.skipif(not _faster_whisper_available(), reason="faster-whisper not installed")
def test_faster_whisper_transcribes_real_audio():
    provider = FasterWhisperProvider(Settings(anthropic_api_key=None))

    result = provider.transcribe(FIXTURE)

    assert isinstance(result, str)
    assert len(result) > 0
