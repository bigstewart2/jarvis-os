from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_manifest_is_not_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("read_note")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_run_returns_content_for_existing_note(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("read_note")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"path": "project-ideas.md"})

    assert result["content"] is not None
    assert "Jarvis OS should eventually search my notes." in result["content"]


def test_run_returns_none_content_for_missing_note(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("read_note")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"path": "does-not-exist.md"})

    assert result["content"] is None
