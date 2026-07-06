import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider


class FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [FakeContentBlock(text)]


class FakeMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeMessage("hello from fake anthropic")


class FakeAnthropicClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.messages = FakeMessages()


def _settings(**overrides) -> Settings:
    defaults = {"anthropic_api_key": "test-key"}
    defaults.update(overrides)
    return Settings(**defaults)


def test_complete_returns_text_from_response(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    result = provider.complete("say hi")

    assert result == "hello from fake anthropic"


def test_complete_sends_prompt_as_user_message(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    provider.complete("say hi")

    sent = provider._client.messages.last_kwargs
    assert sent["messages"] == [{"role": "user", "content": "say hi"}]
    assert "system" not in sent


def test_complete_passes_system_prompt_when_given(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    provider.complete("say hi", system="be terse")

    assert provider._client.messages.last_kwargs["system"] == "be terse"


def test_raises_value_error_without_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(_settings(anthropic_api_key=None))
