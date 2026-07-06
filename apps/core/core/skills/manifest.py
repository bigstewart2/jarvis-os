from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class SkillManifest(BaseModel):
    id: str
    name: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    voice_invokable: bool = False
    background: bool = False
    ui_component: str | None = None


class ManifestError(Exception):
    pass


def load_manifest(manifest_path: Path) -> SkillManifest:
    raw = yaml.safe_load(manifest_path.read_text())
    if raw is None:
        raise ManifestError(f"Empty manifest: {manifest_path}")
    try:
        return SkillManifest(**raw)
    except ValidationError as exc:
        raise ManifestError(f"Invalid manifest {manifest_path}: {exc}") from exc
