from core.providers.llm.base import LLMProvider


class ConformingProvider:
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return f"{system or ''}{prompt}"


def test_conforming_class_satisfies_protocol():
    provider: LLMProvider = ConformingProvider()
    assert provider.complete("hi") == "hi"
    assert provider.complete("hi", system="be terse") == "be tersehi"


def test_isinstance_check_against_protocol():
    provider = ConformingProvider()
    assert isinstance(provider, LLMProvider)
