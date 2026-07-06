import subprocess
from pathlib import Path

from core.config import Settings


class PiperTTSError(Exception):
    pass


class PiperProvider:
    def __init__(self, settings: Settings) -> None:
        self._voice = settings.piper_voice

    def synthesize(self, text: str, output_path: Path) -> None:
        result = subprocess.run(
            ["piper", "--model", self._voice, "--output_file", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise PiperTTSError(f"piper exited with {result.returncode}: {result.stderr}")
