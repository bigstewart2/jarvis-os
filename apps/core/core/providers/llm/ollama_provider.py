import httpx

from core.config import Settings


class OllamaProvider:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict = {"model": self._model, "prompt": prompt, "stream": False}
        if system is not None:
            payload["system"] = system
        response = httpx.post(f"{self._base_url}/api/generate", json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()["response"]
