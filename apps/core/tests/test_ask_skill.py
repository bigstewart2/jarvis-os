from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class FakeProvider:
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return f"echoed: {prompt}"


def test_ask_skill_loads_and_uses_configured_provider(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("ask")
    assert loaded is not None
    assert loaded.manifest.voice_invokable is True

    monkeypatch.setitem(
        loaded.run.__globals__, "get_llm_provider", lambda settings: FakeProvider()
    )

    result = loaded.run({"prompt": "hello"})

    assert result == {"response": "echoed: hello"}
