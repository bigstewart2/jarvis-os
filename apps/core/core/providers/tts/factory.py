from core.config import Settings
from core.providers.tts.base import TTSProvider
from core.providers.tts.piper_provider import PiperProvider


def get_tts_provider(settings: Settings) -> TTSProvider:
    if settings.tts_provider == "piper":
        return PiperProvider(settings)
    raise ValueError(f"Unknown tts_provider: {settings.tts_provider}")
