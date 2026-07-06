from pathlib import Path

from core.config import get_settings
from core.providers.tts.factory import get_tts_provider
from core.voice.files import tts_path

BASE_DIR = Path(__file__).resolve().parents[2]


def run(inputs: dict) -> dict:
    settings = get_settings()
    tts_provider = get_tts_provider(settings)
    voice_dir = BASE_DIR / settings.voice_dir
    output_path = tts_path(voice_dir)
    tts_provider.synthesize(inputs["text"], output_path)
    return {"audio_url": f"/voice/audio/{output_path.stem}", "text": inputs["text"]}
