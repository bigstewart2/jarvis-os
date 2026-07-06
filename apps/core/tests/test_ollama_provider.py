import httpx

from core.config import Settings
from core.providers.llm.ollama_provider import OllamaProvider


class FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error response", request=None, response=self  # type: ignore[arg-type]
            )

    def json(self) -> dict:
        return self._json_data


def test_complete_returns_text_from_response(monkeypatch):
    def fake_post(url, json, timeout):
        return FakeResponse({"response": "hello from fake ollama"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    result = provider.complete("say hi")

    assert result == "hello from fake ollama"


def test_complete_sends_prompt_and_model_no_system_by_default(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "ok"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    provider.complete("say hi")

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"]["prompt"] == "say hi"
    assert captured["json"]["model"] == "llama3.2:3b"
    assert captured["json"]["stream"] is False
    assert "system" not in captured["json"]


def test_complete_passes_system_prompt_when_given(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse({"response": "ok"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    provider.complete("say hi", system="be terse")

    assert captured["json"]["system"] == "be terse"
