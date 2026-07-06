from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    def transcribe(self, audio_path: Path) -> str:
        ...
