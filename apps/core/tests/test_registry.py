from pathlib import Path

from core.skills.registry import SkillRegistry


def _write_fixture_skill(root: Path) -> None:
    skill_dir = root / "greet"
    skill_dir.mkdir()
    (skill_dir / "manifest.yaml").write_text(
        """
id: greet
name: Greet
description: Returns a greeting for the given name.
input_schema:
  type: object
  properties:
    name:
      type: string
output_schema:
  type: object
  properties:
    message:
      type: string
voice_invokable: false
"""
    )
    (skill_dir / "skill.py").write_text(
        "def run(inputs):\n"
        "    return {'message': f\"Hello, {inputs['name']}!\"}\n"
    )


def test_registry_loads_skill_and_runs_it(tmp_path):
    _write_fixture_skill(tmp_path)
    registry = SkillRegistry()
    registry.load_from_directory(tmp_path)

    loaded = registry.get("greet")
    assert loaded is not None
    assert loaded.manifest.name == "Greet"
    assert loaded.run({"name": "Stephen"}) == {"message": "Hello, Stephen!"}


def test_registry_list_returns_all_manifests(tmp_path):
    _write_fixture_skill(tmp_path)
    registry = SkillRegistry()
    registry.load_from_directory(tmp_path)

    manifests = registry.list()
    assert len(manifests) == 1
    assert manifests[0].id == "greet"


def test_registry_get_missing_skill_returns_none(tmp_path):
    registry = SkillRegistry()
    registry.load_from_directory(tmp_path)
    assert registry.get("nonexistent") is None
