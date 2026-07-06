import json
from dataclasses import dataclass

import jsonschema

from core.providers.llm.base import LLMProvider
from core.skills.manifest import SkillManifest

ROUTER_SYSTEM_PROMPT = (
    "You route a user's spoken request to one skill. You will receive the "
    "transcript and a list of available skills with their input schemas. "
    "Respond with ONLY a JSON object, no markdown, no explanation: "
    '{"skill_id": "<id>", "inputs": {<inputs matching that skill\'s input_schema>}}. '
    "If no skill clearly matches the request, or you are not confident, choose "
    '{"skill_id": "ask", "inputs": {"prompt": "<the transcript, verbatim>"}}.'
)


@dataclass
class RouteResult:
    skill_id: str
    inputs: dict
    fallback_used: bool
    fallback_reason: str | None
    raw_response: str


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _build_user_prompt(transcript: str, manifests: list[SkillManifest]) -> str:
    skills_payload = [
        {"id": m.id, "description": m.description, "input_schema": m.input_schema}
        for m in manifests
    ]
    return f"{transcript}\n\n{json.dumps(skills_payload)}"


def route(transcript: str, manifests: list[SkillManifest], llm: LLMProvider) -> RouteResult:
    voice_manifests = [m for m in manifests if m.voice_invokable]
    by_id = {m.id: m for m in voice_manifests}

    raw = llm.complete(_build_user_prompt(transcript, voice_manifests), system=ROUTER_SYSTEM_PROMPT)

    def fallback(reason: str) -> RouteResult:
        return RouteResult(
            skill_id="ask",
            inputs={"prompt": transcript},
            fallback_used=True,
            fallback_reason=reason,
            raw_response=raw,
        )

    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return fallback("json_parse_failure")

    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("skill_id"), str)
        or not isinstance(parsed.get("inputs"), dict)
    ):
        return fallback("wrong_shape")

    skill_id = parsed["skill_id"]
    inputs = parsed["inputs"]

    if skill_id == "ask":
        return fallback("model_chose_ask")

    manifest = by_id.get(skill_id)
    if manifest is None:
        return fallback("unknown_skill_id")

    try:
        jsonschema.validate(inputs, manifest.input_schema)
    except jsonschema.ValidationError:
        return fallback("schema_validation_failure")

    return RouteResult(
        skill_id=skill_id,
        inputs=inputs,
        fallback_used=False,
        fallback_reason=None,
        raw_response=raw,
    )
