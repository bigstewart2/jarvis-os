from core.config import Settings
from core.providers.stt.factory import get_stt_provider
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


def test_returns_faster_whisper_provider():
    settings = Settings(anthropic_api_key=None, stt_provider="faster_whisper")
    provider = get_stt_provider(settings)
    assert isinstance(provider, FasterWhisperProvider)
