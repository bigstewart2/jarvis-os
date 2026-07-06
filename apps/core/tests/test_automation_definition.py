from pathlib import Path

import pytest

from core.automation.definition import DefinitionError, load_definition


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_loads_a_valid_definition(tmp_path):
    path = _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
enabled: true
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: ask
    inputs:
      prompt: "hello"
  - skill: speak
    inputs:
      text: "{{steps.0.response}}"
""")

    definition = load_definition(path)

    assert definition.id == "digest"
    assert definition.name == "Digest"
    assert definition.enabled is True
    assert definition.trigger.type == "cron"
    assert definition.trigger.cron == "0 9 * * *"
    assert len(definition.steps) == 2
    assert definition.steps[0].skill == "ask"
    assert definition.steps[0].inputs == {"prompt": "hello"}
    assert definition.steps[1].inputs == {"text": "{{steps.0.response}}"}


def test_enabled_defaults_to_true(tmp_path):
    path = _write(tmp_path / "digest.yaml", """
id: digest
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: ask
    inputs: {}
""")

    definition = load_definition(path)

    assert definition.enabled is True


def test_empty_file_raises_definition_error(tmp_path):
    path = _write(tmp_path / "digest.yaml", "")

    with pytest.raises(DefinitionError):
        load_definition(path)


def test_missing_required_field_raises_definition_error(tmp_path):
    path = _write(tmp_path / "digest.yaml", """
name: Digest
description: Missing id.
trigger:
  type: cron
  cron: "0 9 * * *"
steps: []
""")

    with pytest.raises(DefinitionError):
        load_definition(path)


def test_malformed_yaml_syntax_raises_definition_error(tmp_path):
    path = tmp_path / "digest.yaml"
    path.write_text("id: digest\nname: [unterminated flow sequence\n")
    with pytest.raises(DefinitionError):
        load_definition(path)


def test_non_mapping_yaml_raises_definition_error(tmp_path):
    path = tmp_path / "digest.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(DefinitionError):
        load_definition(path)


def test_non_utf8_binary_file_raises_definition_error(tmp_path):
    path = tmp_path / "digest.yaml"
    path.write_bytes(b"\xff\xfe\x00\x01binary garbage not utf-8 \x80\x81")

    with pytest.raises(DefinitionError):
        load_definition(path)


def test_id_not_matching_filename_raises_definition_error(tmp_path):
    path = _write(tmp_path / "digest.yaml", """
id: wrong_id
name: Digest
description: A test automation.
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: ask
    inputs: {}
""")

    with pytest.raises(DefinitionError, match="wrong_id"):
        load_definition(path)
