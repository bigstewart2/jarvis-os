from pathlib import Path

from faster_whisper import WhisperModel

from core.config import Settings


class FasterWhisperProvider:
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.stt_model
        self._compute_type = settings.stt_compute_type
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self._model_name, compute_type=self._compute_type)
        return self._model

    def transcribe(self, audio_path: Path) -> str:
        model = self._get_model()
        segments, _info = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments).strip()
