from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class TriggerDefinition(BaseModel):
    type: str
    cron: str


class StepDefinition(BaseModel):
    skill: str
    inputs: dict = Field(default_factory=dict)


class AutomationDefinition(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool = True
    trigger: TriggerDefinition
    steps: list[StepDefinition]


class DefinitionError(Exception):
    pass


def load_definition(definition_path: Path) -> AutomationDefinition:
    try:
        raw = yaml.safe_load(definition_path.read_text())
    except yaml.YAMLError as exc:
        raise DefinitionError(f"Malformed YAML in automation definition {definition_path}: {exc}") from exc
    if raw is None:
        raise DefinitionError(f"Empty automation definition: {definition_path}")
    if not isinstance(raw, dict):
        raise DefinitionError(
            f"Automation definition must be a YAML mapping, got {type(raw).__name__}: {definition_path}"
        )
    try:
        definition = AutomationDefinition(**raw)
    except ValidationError as exc:
        raise DefinitionError(f"Invalid automation definition {definition_path}: {exc}") from exc
    if definition.id != definition_path.stem:
        raise DefinitionError(
            f"Automation id '{definition.id}' does not match filename '{definition_path.stem}' in {definition_path}"
        )
    return definition
