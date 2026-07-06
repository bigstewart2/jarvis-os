from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.base import LLMProvider
from core.providers.llm.ollama_provider import OllamaProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings)
    raise ValueError(f"Unknown llm_provider: {settings.llm_provider}")
