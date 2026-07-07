import sys
from pathlib import Path

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import BASE_DIR, PiperProvider

PIPER_BIN = Path(sys.executable).parent / "piper"


def _default_model_path() -> Path:
    settings = Settings(anthropic_api_key=None)
    return BASE_DIR / settings.piper_voices_dir / f"{settings.piper_voice}.onnx"


@pytest.mark.skipif(not PIPER_BIN.exists(), reason="piper CLI not installed in venv")
@pytest.mark.skipif(not _default_model_path().exists(), reason="default voice model not downloaded")
def test_piper_produces_nonempty_wav(tmp_path):
    provider = PiperProvider(Settings(anthropic_api_key=None))
    output_path = tmp_path / "out.wav"

    provider.synthesize("This is a test.", output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
