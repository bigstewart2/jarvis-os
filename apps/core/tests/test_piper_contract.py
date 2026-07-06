import shutil

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import PiperProvider


@pytest.mark.skipif(shutil.which("piper") is None, reason="piper CLI not installed")
def test_piper_produces_nonempty_wav(tmp_path):
    provider = PiperProvider(Settings(anthropic_api_key=None))
    output_path = tmp_path / "out.wav"

    provider.synthesize("This is a test.", output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
