import subprocess
import sys
from pathlib import Path

from core.config import Settings

BASE_DIR = Path(__file__).resolve().parents[3]


class PiperTTSError(Exception):
    pass


class PiperProvider:
    def __init__(self, settings: Settings) -> None:
        self._voice = settings.piper_voice
        self._voices_dir = BASE_DIR / settings.piper_voices_dir

    def synthesize(self, text: str, output_path: Path) -> None:
        model_path = self._voices_dir / f"{self._voice}.onnx"
        if not model_path.exists():
            raise PiperTTSError(
                f"Voice model not found: {model_path}. "
                f"Download it with: .venv/bin/python -m piper.download_voices {self._voice} "
                f"(run from apps/core, then move the .onnx/.onnx.json files into {self._voices_dir})"
            )
        # Use the venv's piper entry point so PATH doesn't matter — bare "piper"
        # is not on PATH when uvicorn runs from the venv.
        piper_bin = Path(sys.executable).parent / "piper"
        result = subprocess.run(
            [str(piper_bin), "--model", str(model_path), "--output_file", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise PiperTTSError(f"piper exited with {result.returncode}: {result.stderr}")
