import shutil
import time
import uuid
from pathlib import Path


def upload_path(voice_dir: Path, extension: str = "webm") -> Path:
    uploads_dir = voice_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir / f"{uuid.uuid4()}.{extension}"


def tts_path(voice_dir: Path) -> Path:
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    return tts_dir / f"{uuid.uuid4()}.wav"


def prune_tts_files(voice_dir: Path, max_age_seconds: float = 3600.0, keep_newest: int = 20) -> None:
    tts_dir = voice_dir / "tts"
    if not tts_dir.exists():
        return
    files = sorted(tts_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    now = time.time()
    for index, path in enumerate(files):
        if index < keep_newest:
            continue
        if now - path.stat().st_mtime > max_age_seconds:
            path.unlink()


def clear_voice_dir(voice_dir: Path) -> None:
    if voice_dir.exists():
        shutil.rmtree(voice_dir)
    voice_dir.mkdir(parents=True, exist_ok=True)
