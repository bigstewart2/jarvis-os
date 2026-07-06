from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def test_real_echo_skill_loads_and_runs():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("echo")
    assert loaded is not None
    assert loaded.manifest.voice_invokable is True
    assert loaded.run({"text": "hello jarvis"}) == {"text": "hello jarvis"}
