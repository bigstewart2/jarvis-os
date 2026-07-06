import httpx
import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.ollama_provider import OllamaProvider

PROMPT = "Say the word 'test' and nothing else."


def _ollama_reachable(base_url: str) -> bool:
    try:
        httpx.get(base_url, timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


_settings = Settings()
_anthropic_available = bool(_settings.anthropic_api_key)
_ollama_available = _ollama_reachable(_settings.ollama_base_url)


@pytest.mark.skipif(not _anthropic_available, reason="ANTHROPIC_API_KEY not configured")
def test_anthropic_provider_completes_real_prompt():
    provider = AnthropicProvider(_settings)
    result = provider.complete(PROMPT)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.skipif(not _ollama_available, reason="Ollama not reachable at configured base URL")
def test_ollama_provider_completes_real_prompt():
    provider = OllamaProvider(_settings)
    result = provider.complete(PROMPT)
    assert isinstance(result, str)
    assert len(result) > 0
