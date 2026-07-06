import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.factory import get_llm_provider
from core.providers.llm.ollama_provider import OllamaProvider


def test_returns_anthropic_provider_when_configured():
    settings = Settings(llm_provider="anthropic", anthropic_api_key="test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, AnthropicProvider)


def test_returns_ollama_provider_when_configured():
    settings = Settings(llm_provider="ollama", anthropic_api_key=None)
    provider = get_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)


def test_raises_on_unknown_provider_name():
    settings = Settings(anthropic_api_key=None)
    settings.llm_provider = "bogus"
    with pytest.raises(ValueError, match="bogus"):
        get_llm_provider(settings)
