from dataclasses import dataclass
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger

from core.automation.definition import AutomationDefinition, DefinitionError, load_definition
from core.automation.template import extract_referenced_step_indices
from core.skills.registry import SkillRegistry


@dataclass
class LoadedAutomation:
    automation_id: str
    definition: AutomationDefinition | None
    load_error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.definition is not None


class AutomationRegistry:
    def __init__(self, skill_registry: SkillRegistry) -> None:
        self._skill_registry = skill_registry
        self._automations: dict[str, LoadedAutomation] = {}

    def load_from_directory(self, automations_dir: Path) -> None:
        if not automations_dir.exists():
            return
        for path in sorted(automations_dir.glob("*.yaml")):
            automation_id = path.stem
            try:
                definition = load_definition(path)
                self._validate(definition)
                self._automations[automation_id] = LoadedAutomation(
                    automation_id=automation_id, definition=definition
                )
            except DefinitionError as exc:
                self._automations[automation_id] = LoadedAutomation(
                    automation_id=automation_id, definition=None, load_error=str(exc)
                )

    def _validate(self, definition: AutomationDefinition) -> None:
        if definition.trigger.type != "cron":
            raise DefinitionError(f"Unsupported trigger type: {definition.trigger.type}")
        try:
            CronTrigger.from_crontab(definition.trigger.cron)
        except Exception as exc:
            raise DefinitionError(f"Invalid cron expression '{definition.trigger.cron}': {exc}") from exc
        for index, step in enumerate(definition.steps):
            if self._skill_registry.get(step.skill) is None:
                raise DefinitionError(f"Step {index} references unknown skill '{step.skill}'")
            referenced = extract_referenced_step_indices(step.inputs)
            for ref_index in referenced:
                if ref_index >= index:
                    raise DefinitionError(
                        f"Step {index} references step {ref_index}, which is not an earlier step"
                    )

    def get(self, automation_id: str) -> LoadedAutomation | None:
        return self._automations.get(automation_id)

    def list(self) -> list[LoadedAutomation]:
        return list(self._automations.values())
