from core.config import Settings
from core.providers.stt.base import STTProvider
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


def get_stt_provider(settings: Settings) -> STTProvider:
    if settings.stt_provider == "faster_whisper":
        return FasterWhisperProvider(settings)
    raise ValueError(f"Unknown stt_provider: {settings.stt_provider}")
