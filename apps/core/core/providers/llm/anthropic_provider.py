from anthropic import Anthropic

from core.config import Settings


class AnthropicProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY (or JARVIS_ANTHROPIC_API_KEY) is not set; "
                "cannot construct AnthropicProvider"
            )
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        kwargs: dict = {}
        if system is not None:
            kwargs["system"] = system
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return message.content[0].text
