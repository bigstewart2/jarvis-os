from pathlib import Path

from core.automation.registry import AutomationRegistry
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill, SkillRegistry


def _skill_registry_with_echo() -> SkillRegistry:
    registry = SkillRegistry()
    manifest = SkillManifest(id="echo", name="Echo", description="Echoes", input_schema={}, output_schema={})
    registry._skills["echo"] = LoadedSkill(manifest=manifest, run=lambda inputs: inputs)
    return registry


def _write(path: Path, content: str) -> None:
    path.write_text(content)


def test_loads_a_valid_single_step_automation(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
enabled: true
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs:
      text: "hello"
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    loaded = registry.get("digest")

    assert loaded is not None
    assert loaded.is_valid
    assert loaded.definition.id == "digest"
    assert loaded.load_error is None


def test_loads_a_two_step_automation_with_valid_wiring(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
enabled: true
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs:
      text: "hello"
  - skill: echo
    inputs:
      text: "{{steps.0.text}}"
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    assert registry.get("digest").is_valid


def test_bad_cron_marks_invalid_not_fatal(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "not a cron expression"
steps:
  - skill: echo
    inputs: {}
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    loaded = registry.get("digest")

    assert loaded is not None
    assert not loaded.is_valid
    assert "cron" in loaded.load_error.lower()


def test_unknown_skill_marks_invalid(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: does-not-exist
    inputs: {}
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    loaded = registry.get("digest")

    assert not loaded.is_valid
    assert "does-not-exist" in loaded.load_error


def test_forward_reference_marks_invalid(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs:
      text: "{{steps.1.text}}"
  - skill: echo
    inputs:
      text: "hello"
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    loaded = registry.get("digest")

    assert not loaded.is_valid
    assert "step 0" in loaded.load_error.lower()


def test_id_filename_mismatch_marks_invalid(tmp_path):
    _write(tmp_path / "digest.yaml", """
id: wrong_id
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs: {}
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    assert not registry.get("digest").is_valid


def test_invalid_automation_does_not_prevent_others_from_loading(tmp_path):
    _write(tmp_path / "bad.yaml", """
id: bad
name: Bad
description: Invalid.
trigger:
  type: cron
  cron: "garbage"
steps:
  - skill: echo
    inputs: {}
""")
    _write(tmp_path / "good.yaml", """
id: good
name: Good
description: Valid.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs: {}
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    assert not registry.get("bad").is_valid
    assert registry.get("good").is_valid


def test_malformed_yaml_file_does_not_prevent_others_from_loading(tmp_path):
    _write(tmp_path / "bad.yaml", """
id: bad
name: [unterminated
""")
    _write(tmp_path / "good.yaml", """
id: good
name: Good
description: Valid.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: echo
    inputs: {}
""")
    registry = AutomationRegistry(_skill_registry_with_echo())
    registry.load_from_directory(tmp_path)

    assert not registry.get("bad").is_valid
    assert registry.get("good").is_valid
