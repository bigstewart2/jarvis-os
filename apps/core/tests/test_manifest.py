import pytest

from core.skills.manifest import ManifestError, load_manifest


def test_load_valid_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
id: echo
name: Echo
description: Repeats the input text back.
input_schema:
  type: object
  properties:
    text:
      type: string
output_schema:
  type: object
  properties:
    text:
      type: string
voice_invokable: true
"""
    )
    manifest = load_manifest(manifest_path)
    assert manifest.id == "echo"
    assert manifest.voice_invokable is True
    assert manifest.ui_component is None


def test_load_manifest_missing_required_field(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("name: Echo\ndescription: Missing id field.\n")
    with pytest.raises(ManifestError):
        load_manifest(manifest_path)
