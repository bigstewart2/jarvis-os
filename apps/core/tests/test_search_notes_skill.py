from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_manifest_is_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("search_notes")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is True


def test_run_returns_matches_from_configured_vault(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("search_notes")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"query": "jarvis"})

    assert len(result["matches"]) == 1
    assert result["matches"][0]["path"] == "project-ideas.md"
    assert result["matches"][0]["title"] == "Project Ideas"


def test_run_returns_empty_matches_for_no_hits(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("search_notes")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"query": "zzzznomatchzzzz"})

    assert result["matches"] == []
