from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> None:
        ...
