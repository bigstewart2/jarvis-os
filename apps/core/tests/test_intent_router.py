import pytest

from core.routing.intent_router import RouteResult, route
from core.skills.manifest import SkillManifest


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.last_prompt = prompt
        self.last_system = system
        return self.response


ECHO_MANIFEST = SkillManifest(
    id="echo",
    name="Echo",
    description="Repeats back text",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    voice_invokable=True,
)

ASK_MANIFEST = SkillManifest(
    id="ask",
    name="Ask",
    description="General question answering",
    input_schema={
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    },
    output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
    voice_invokable=True,
)

MANIFESTS = [ECHO_MANIFEST, ASK_MANIFEST]


def test_routes_to_matching_skill():
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"text": "hello"}}')

    result = route("say hello", MANIFESTS, llm)

    assert result == RouteResult(
        skill_id="echo",
        inputs={"text": "hello"},
        fallback_used=False,
        fallback_reason=None,
        raw_response=llm.response,
    )


def test_strips_json_code_fence():
    llm = FakeLLM('```json\n{"skill_id": "echo", "inputs": {"text": "hi"}}\n```')

    result = route("say hi", MANIFESTS, llm)

    assert result.skill_id == "echo"
    assert result.fallback_used is False


def test_falls_back_on_json_parse_failure():
    llm = FakeLLM("not json at all")

    result = route("garble garble", MANIFESTS, llm)

    assert result.skill_id == "ask"
    assert result.fallback_used is True
    assert result.fallback_reason == "json_parse_failure"
    assert result.inputs == {"prompt": "garble garble"}


def test_falls_back_on_wrong_shape():
    llm = FakeLLM('{"skill_id": "echo"}')

    result = route("say hello", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "wrong_shape"


def test_falls_back_on_unknown_skill_id():
    llm = FakeLLM('{"skill_id": "does-not-exist", "inputs": {}}')

    result = route("do something", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "unknown_skill_id"


def test_falls_back_on_schema_validation_failure():
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"wrong_field": "x"}}')

    result = route("say hello", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "schema_validation_failure"


def test_falls_back_when_model_chooses_ask():
    llm = FakeLLM('{"skill_id": "ask", "inputs": {"prompt": "what is 2 plus 2"}}')

    result = route("what is 2 plus 2", MANIFESTS, llm)

    assert result.skill_id == "ask"
    assert result.fallback_used is True
    assert result.fallback_reason == "model_chose_ask"


def test_llm_exception_propagates():
    class RaisingLLM:
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        route("hello", MANIFESTS, RaisingLLM())


def test_only_voice_invokable_manifests_sent_to_llm():
    hidden = SkillManifest(
        id="hidden",
        name="Hidden",
        description="not voice invokable",
        input_schema={},
        output_schema={},
        voice_invokable=False,
    )
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"text": "hi"}}')

    route("say hi", [ECHO_MANIFEST, ASK_MANIFEST, hidden], llm)

    assert "hidden" not in llm.last_prompt
