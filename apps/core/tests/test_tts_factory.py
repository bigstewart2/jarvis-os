from core.config import Settings
from core.providers.tts.factory import get_tts_provider
from core.providers.tts.piper_provider import PiperProvider


def test_returns_piper_provider():
    settings = Settings(anthropic_api_key=None, tts_provider="piper")
    provider = get_tts_provider(settings)
    assert isinstance(provider, PiperProvider)
