from core.config import get_settings
from core.providers.llm.factory import get_llm_provider


def run(inputs: dict) -> dict:
    settings = get_settings()
    provider = get_llm_provider(settings)
    response = provider.complete(inputs["prompt"])
    return {"response": response}
