# Jarvis OS Milestone 6: Automation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cron-scheduled automation engine — YAML-defined pipelines of skill calls with output→input wiring — proven by one real automation (`ask_digest`: `ask` → `speak`).

**Architecture:** Automations are YAML files loaded at startup like skills (`AutomationRegistry`, invalid files visible-but-inert). A new `AutomationRunner` executes a pipeline's steps in order through the existing, unchanged `invoke_and_record_skill` path, publishing `automation_run` WebSocket events and writing a durable `AutomationRun` DB record with a `finally`-guaranteed single terminal state. `APScheduler`'s `AsyncIOScheduler` fires cron jobs directly on the FastAPI event loop, calling the exact same `runner.start()` a manual trigger endpoint calls.

**Tech Stack:** Python 3.14, FastAPI (existing), `apscheduler` (new dependency, `AsyncIOScheduler` + `CronTrigger`), SQLAlchemy 2.0 (existing). Backend-only milestone — no frontend UI task, matching Milestone 5's precedent.

## Global Constraints

- Run all commands from `apps/core/` using `.venv/bin/python3` / `.venv/bin/pytest`.
- New dependency: `apscheduler>=3.10`, added to `apps/core/requirements.txt` with a flexible `>=` pin.
- Every task ends with a full `.venv/bin/pytest -v` run.
- Automation definitions live in `apps/core/automations/*.yaml`, one file per automation, loaded at startup by `AutomationRegistry.load_from_directory`.
- **An invalid automation file must never crash startup and must never be silently skipped.** It is registered with `status: invalid` and a `load_error` message, excluded from scheduling and manual triggering, and visible via `GET /automations`.
- Wiring mechanism is exactly `{{steps.N.path}}` token substitution — no template language, no Jinja. A whole-string token preserves the referenced value's type; an embedded token stringifies. A path that resolves to nothing raises a render error — never a silent empty string.
- Pipeline execution is strictly sequential with **fail-fast** error handling: the first failed step (or render error) terminates the run immediately with `failed_step` recorded; no later step executes.
- Every automation run reaches **exactly one terminal state** (`completed`, `failed`, or `interrupted` at next startup for restart orphans), structurally guaranteed by a try/except/finally-equivalent in the runner — a run can never be silently stuck `running`.
- Every pipeline step goes through the existing `invoke_and_record_skill(app, skill_id, inputs)` — no second invocation path.
- Scheduler jobs use `coalesce=True`, `misfire_grace_time=60`, `max_instances=1`.
- WebSocket event shape: `{"type": "automation_run", "run_id": "<uuid>", "automation_id": "<id>", "stage": "<stage>", "detail": {...}}` with stages `started`, `step_started`, `step_completed`, `completed`, `failed`.
- No auto-commit, no retries, no branching/conditionals, no event-based triggers this milestone.

---

### Task 1: Config extension + apscheduler dependency

**Files:**
- Modify: `apps/core/core/config.py`
- Modify: `apps/core/tests/test_config.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Produces: `Settings.automations_dir: str` — every later task that loads automation definitions reads this off a `Settings` instance.

- [ ] **Step 1: Write the failing config test**

Append to `apps/core/tests/test_config.py`:
```python
def test_automations_dir_default():
    settings = Settings(anthropic_api_key=None)
    assert settings.automations_dir == "automations"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py::test_automations_dir_default -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'automations_dir'`.

- [ ] **Step 3: Extend Settings**

Read the current contents of `apps/core/core/config.py` first, then add this field to the `Settings` class (after the existing `claude_code_max_turns` field, before `def get_settings()`):
```python
    automations_dir: str = "automations"
```

- [ ] **Step 4: Run config test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 5: Add the apscheduler dependency**

Append to `apps/core/requirements.txt`:
```
apscheduler>=3.10
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 116 passed, 1 skipped (115 from Milestone 5, plus 1 new config test).

- [ ] **Step 7: Commit**

```bash
git add core/config.py tests/test_config.py requirements.txt
git commit -m "feat(core): add automations_dir setting and apscheduler dependency"
```

---

### Task 2: AutomationDefinition + load_definition

**Files:**
- Create: `apps/core/core/automation/__init__.py` (empty)
- Create: `apps/core/core/automation/definition.py`
- Create: `apps/core/tests/test_automation_definition.py`

**Interfaces:**
- Produces: `TriggerDefinition` (fields: `type: str`, `cron: str`), `StepDefinition` (fields: `skill: str`, `inputs: dict`), `AutomationDefinition` (fields: `id: str`, `name: str`, `description: str`, `enabled: bool = True`, `trigger: TriggerDefinition`, `steps: list[StepDefinition]`), `DefinitionError`, `load_definition(definition_path: Path) -> AutomationDefinition`. Later tasks (registry, runner, endpoints) all consume these types directly.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_automation_definition.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_definition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.automation'`.

- [ ] **Step 3: Implement the definition model and loader**

Create `apps/core/core/automation/__init__.py` (empty file).

Create `apps/core/core/automation/definition.py`:
```python
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
    raw = yaml.safe_load(definition_path.read_text())
    if raw is None:
        raise DefinitionError(f"Empty automation definition: {definition_path}")
    try:
        definition = AutomationDefinition(**raw)
    except ValidationError as exc:
        raise DefinitionError(f"Invalid automation definition {definition_path}: {exc}") from exc
    if definition.id != definition_path.stem:
        raise DefinitionError(
            f"Automation id '{definition.id}' does not match filename '{definition_path.stem}' in {definition_path}"
        )
    return definition
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_definition.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 121 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/automation/__init__.py core/automation/definition.py tests/test_automation_definition.py
git commit -m "feat(core): add AutomationDefinition model and loader"
```

---

### Task 3: Output→input wiring (render_inputs)

**Files:**
- Create: `apps/core/core/automation/template.py`
- Create: `apps/core/tests/test_automation_template.py`

**Interfaces:**
- Produces: `RenderError`, `render_inputs(template, step_outputs: list[dict])` (recursively resolves `{{steps.N.path}}` tokens; whole-string tokens preserve type, embedded tokens stringify; raises `RenderError` on any unresolvable reference), `extract_referenced_step_indices(template) -> set[int]` (recursively collects every step index referenced anywhere in a template, without resolving values — used by the registry's forward-reference validation in Task 5). Both are pure functions — no I/O, no side effects.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_automation_template.py`:
```python
import pytest

from core.automation.template import RenderError, extract_referenced_step_indices, render_inputs


def test_whole_string_token_preserves_type():
    result = render_inputs("{{steps.0.response}}", [{"response": {"nested": "value"}}])
    assert result == {"nested": "value"}


def test_embedded_token_stringifies():
    result = render_inputs("Say: {{steps.0.response}}", [{"response": "hello"}])
    assert result == "Say: hello"


def test_nested_dict_and_list_recursion():
    template = {"a": ["{{steps.0.x}}", {"b": "{{steps.0.y}}"}]}
    result = render_inputs(template, [{"x": "1", "y": "2"}])
    assert result == {"a": ["1", {"b": "2"}]}


def test_dotted_path_traversal():
    result = render_inputs("{{steps.0.a.b}}", [{"a": {"b": "deep"}}])
    assert result == "deep"


def test_missing_key_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.0.missing}}", [{"response": "hi"}])


def test_non_dict_traversal_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.0.a.b}}", [{"a": "not a dict"}])


def test_out_of_range_index_raises_render_error():
    with pytest.raises(RenderError):
        render_inputs("{{steps.5.response}}", [{"response": "hi"}])


def test_multiple_tokens_in_one_string():
    result = render_inputs("{{steps.0.a}} and {{steps.1.b}}", [{"a": "x"}, {"b": "y"}])
    assert result == "x and y"


def test_token_free_template_passes_through():
    result = render_inputs("plain text", [{"a": "x"}])
    assert result == "plain text"


def test_non_string_scalar_passes_through():
    result = render_inputs(42, [{"a": "x"}])
    assert result == 42


def test_extract_referenced_step_indices_finds_all_indices():
    template = {"a": "{{steps.0.x}}", "b": ["{{steps.2.y}}", "no token here"]}
    assert extract_referenced_step_indices(template) == {0, 2}


def test_extract_referenced_step_indices_empty_for_no_tokens():
    assert extract_referenced_step_indices({"a": "plain", "b": 42}) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_template.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.automation.template'`.

- [ ] **Step 3: Implement the wiring mechanism**

Create `apps/core/core/automation/template.py`:
```python
import re

TOKEN_PATTERN = re.compile(r"\{\{steps\.(\d+)\.([\w.]+)\}\}")
_WHOLE_TOKEN_PATTERN = re.compile(r"^\{\{steps\.(\d+)\.([\w.]+)\}\}$")


class RenderError(Exception):
    pass


def _resolve_path(step_outputs: list[dict], index: int, path: str):
    if index < 0 or index >= len(step_outputs):
        raise RenderError(f"step index {index} out of range (have {len(step_outputs)} prior step outputs)")
    value = step_outputs[index]
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise RenderError(f"path '{path}' not found in step {index}'s outputs")
        value = value[part]
    return value


def _render_string(template: str, step_outputs: list[dict]):
    whole_match = _WHOLE_TOKEN_PATTERN.match(template)
    if whole_match:
        index = int(whole_match.group(1))
        path = whole_match.group(2)
        return _resolve_path(step_outputs, index, path)

    def _replace(match: "re.Match") -> str:
        index = int(match.group(1))
        path = match.group(2)
        return str(_resolve_path(step_outputs, index, path))

    return TOKEN_PATTERN.sub(_replace, template)


def render_inputs(template, step_outputs: list[dict]):
    if isinstance(template, str):
        return _render_string(template, step_outputs)
    if isinstance(template, dict):
        return {key: render_inputs(value, step_outputs) for key, value in template.items()}
    if isinstance(template, list):
        return [render_inputs(item, step_outputs) for item in template]
    return template


def extract_referenced_step_indices(template) -> set:
    indices: set = set()
    if isinstance(template, str):
        for match in TOKEN_PATTERN.finditer(template):
            indices.add(int(match.group(1)))
    elif isinstance(template, dict):
        for value in template.values():
            indices |= extract_referenced_step_indices(value)
    elif isinstance(template, list):
        for item in template:
            indices |= extract_referenced_step_indices(item)
    return indices
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_template.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 133 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/automation/template.py tests/test_automation_template.py
git commit -m "feat(core): add automation output-to-input wiring (render_inputs)"
```

---

### Task 4: AutomationRun DB model

**Files:**
- Modify: `apps/core/core/db/models.py`
- Modify: `apps/core/tests/test_db.py`

**Interfaces:**
- Produces: `AutomationRun` SQLAlchemy model with columns `run_id` (str, PK), `automation_id`, `trigger`, `status`, `steps` (JSON list), `failed_step`, `error`, `started_at`, `finished_at`. `AutomationRunner` (Task 6) and the endpoints (Task 8) both read/write this table.

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_db.py`:
```python
def test_automation_run_can_be_created_and_queried():
    from core.db.models import AutomationRun

    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        session.add(
            AutomationRun(
                run_id="abc-123",
                automation_id="digest",
                trigger="manual",
                status="running",
                steps=[],
            )
        )
        session.commit()

    with session_factory() as session:
        row = session.get(AutomationRun, "abc-123")
        assert row.automation_id == "digest"
        assert row.trigger == "manual"
        assert row.status == "running"
        assert row.steps == []
        assert row.failed_step is None
        assert row.error is None
        assert row.started_at is not None
        assert row.finished_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py::test_automation_run_can_be_created_and_queried -v`
Expected: FAIL — `ImportError: cannot import name 'AutomationRun'`.

- [ ] **Step 3: Add the model**

Read the current contents of `apps/core/core/db/models.py` first. Add this class after `ClaudeCodeTask`:
```python
class AutomationRun(Base):
    __tablename__ = "automation_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    automation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failed_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

No new imports needed — `Boolean, DateTime, Float, Integer, JSON, String` are already imported, and `Mapped`/`mapped_column`/`datetime`/`timezone` are already in scope from the existing file.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 134 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/db/models.py tests/test_db.py
git commit -m "feat(core): add AutomationRun DB model"
```

---

### Task 5: AutomationRegistry

**Files:**
- Create: `apps/core/core/automation/registry.py`
- Create: `apps/core/tests/test_automation_registry.py`
- Modify: `apps/core/requirements.txt` (no change needed — apscheduler already added in Task 1; this task just imports `CronTrigger` from it)

**Interfaces:**
- Consumes: `AutomationDefinition`, `DefinitionError`, `load_definition` (Task 2), `extract_referenced_step_indices` (Task 3), `SkillRegistry` (existing, M1).
- Produces: `LoadedAutomation` dataclass (`automation_id: str`, `definition: AutomationDefinition | None`, `load_error: str | None = None`, property `is_valid`), `AutomationRegistry(skill_registry: SkillRegistry)` with `load_from_directory(automations_dir: Path) -> None`, `get(automation_id) -> LoadedAutomation | None`, `list() -> list[LoadedAutomation]`. Later tasks (runner, scheduler, endpoints) all consume this registry.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_automation_registry.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.automation.registry'`.

- [ ] **Step 3: Implement the registry**

Create `apps/core/core/automation/registry.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_registry.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 141 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/automation/registry.py tests/test_automation_registry.py
git commit -m "feat(core): add AutomationRegistry with load-time validation"
```

---

### Task 6: AutomationRunner

**Files:**
- Create: `apps/core/core/automation/runner.py`
- Create: `apps/core/tests/test_automation_runner.py`

**Interfaces:**
- Consumes: `RenderError`/`render_inputs` (Task 3), `AutomationRun` (Task 4), `LoadedAutomation`/`AutomationRegistry` (Task 5), `invoke_and_record_skill` (existing, M4).
- Produces: `AutomationRunner(automation_registry: AutomationRegistry, app)` with `async def start(automation_id: str, trigger: str) -> str` — creates the DB row, schedules `_run` as an `asyncio.create_task`, returns a `run_id` immediately. Endpoints (Task 8) and the scheduler (Task 7) both call `start()`.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_automation_runner.py`:
```python
import asyncio

from core.app import create_app
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import AutomationRegistry, LoadedAutomation
from core.automation.runner import AutomationRunner
from core.db.models import AutomationRun
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill


def _register_stub_skill(app, skill_id, run_fn):
    manifest = SkillManifest(id=skill_id, name=skill_id, description="stub", input_schema={}, output_schema={})
    app.state.registry._skills[skill_id] = LoadedSkill(manifest=manifest, run=run_fn)


def _make_app_and_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    automation_registry = AutomationRegistry(app.state.registry)
    runner = AutomationRunner(automation_registry, app)
    return app, automation_registry, runner


async def _collect_until(queue, terminal_stages):
    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=5.0)
        events.append(event)
        if event["stage"] in terminal_stages:
            break
    return events


def test_happy_two_step_run_wires_output_to_input(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    _register_stub_skill(app, "step_one", lambda inputs: {"value": "hello"})
    _register_stub_skill(app, "step_two", lambda inputs: {"received": inputs["text"]})

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={}),
            StepDefinition(skill="step_two", inputs={"text": "{{steps.0.value}}"}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    stages = [e["stage"] for e in events]
    assert stages == ["started", "step_started", "step_completed", "step_started", "step_completed", "completed"]

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "completed"
        assert row.steps == [
            {"skill_id": "step_one", "status": "completed"},
            {"skill_id": "step_two", "status": "completed"},
        ]


def test_step_failure_stops_pipeline_and_records_failed_step(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    calls = []

    def failing_run(inputs):
        raise RuntimeError("boom")

    def step_two_run(inputs):
        calls.append("ran")
        return {"ok": True}

    _register_stub_skill(app, "step_one", failing_run)
    _register_stub_skill(app, "step_two", step_two_run)

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={}),
            StepDefinition(skill="step_two", inputs={}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"
    assert events[-1]["detail"]["failed_step"] == 0
    assert calls == []

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
        assert row.failed_step == 0


def test_render_error_fails_run_before_invoking_skill(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    calls = []

    def step_one_run(inputs):
        calls.append("ran")
        return {"ok": True}

    _register_stub_skill(app, "step_one", step_one_run)

    definition = AutomationDefinition(
        id="digest", name="Digest", description="test", enabled=True,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[
            StepDefinition(skill="step_one", inputs={"text": "{{steps.5.missing}}"}),
        ],
    )
    automation_registry._automations["digest"] = LoadedAutomation(automation_id="digest", definition=definition)

    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("digest", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"
    assert "render_error" in events[-1]["detail"]["error"]
    assert calls == []

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
        assert row.failed_step == 0


def test_unknown_automation_id_still_writes_terminal_failed_state(tmp_path, monkeypatch):
    app, automation_registry, runner = _make_app_and_runner(tmp_path, monkeypatch)
    queue = app.state.event_bus.subscribe()

    async def run():
        run_id = await runner.start("does-not-exist", "manual")
        events = await _collect_until(queue, ("completed", "failed"))
        return run_id, events

    run_id, events = asyncio.run(run())

    assert events[-1]["stage"] == "failed"

    with app.state.session_factory() as session:
        row = session.get(AutomationRun, run_id)
        assert row.status == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.automation.runner'`.

- [ ] **Step 3: Implement the runner**

Create `apps/core/core/automation/runner.py`:
```python
import asyncio
import uuid
from datetime import datetime, timezone

from core.automation.template import RenderError, render_inputs
from core.db.models import AutomationRun
from core.skills.invocation import invoke_and_record_skill


class AutomationRunner:
    def __init__(self, automation_registry, app) -> None:
        self._automation_registry = automation_registry
        self._app = app

    async def start(self, automation_id: str, trigger: str) -> str:
        run_id = str(uuid.uuid4())
        with self._app.state.session_factory() as session:
            session.add(
                AutomationRun(
                    run_id=run_id, automation_id=automation_id, trigger=trigger, status="running", steps=[]
                )
            )
            session.commit()

        asyncio.create_task(self._run(run_id, automation_id, trigger))
        return run_id

    async def _publish(self, run_id: str, automation_id: str, stage: str, detail: dict) -> None:
        await self._app.state.event_bus.publish(
            {
                "type": "automation_run",
                "run_id": run_id,
                "automation_id": automation_id,
                "stage": stage,
                "detail": detail,
            }
        )

    def _write_terminal_state(self, run_id: str, status: str, **fields) -> None:
        with self._app.state.session_factory() as session:
            row = session.get(AutomationRun, run_id)
            row.status = status
            for key, value in fields.items():
                setattr(row, key, value)
            row.finished_at = datetime.now(timezone.utc)
            session.commit()

    def _append_step_result(self, run_id: str, step_result: dict) -> None:
        with self._app.state.session_factory() as session:
            row = session.get(AutomationRun, run_id)
            row.steps = row.steps + [step_result]
            session.commit()

    async def _run(self, run_id: str, automation_id: str, trigger: str) -> None:
        try:
            loaded = self._automation_registry.get(automation_id)
            if loaded is None or not loaded.is_valid:
                raise RuntimeError(f"Automation '{automation_id}' is not loaded or invalid")
            definition = loaded.definition

            await self._publish(
                run_id, automation_id, "started", {"trigger": trigger, "num_steps": len(definition.steps)}
            )

            step_outputs: list[dict] = []
            for index, step in enumerate(definition.steps):
                await self._publish(run_id, automation_id, "step_started", {"index": index, "skill_id": step.skill})

                try:
                    inputs = render_inputs(step.inputs, step_outputs)
                except RenderError as exc:
                    error_message = f"render_error: {exc}"
                    self._append_step_result(
                        run_id, {"skill_id": step.skill, "status": "failed", "error": error_message}
                    )
                    self._write_terminal_state(run_id, "failed", failed_step=index, error=error_message)
                    await self._publish(
                        run_id, automation_id, "failed", {"failed_step": index, "error": error_message}
                    )
                    return

                status, outputs = await invoke_and_record_skill(self._app, step.skill, inputs)
                if status == "failed":
                    error_message = outputs.get("error")
                    self._append_step_result(
                        run_id, {"skill_id": step.skill, "status": "failed", "error": error_message}
                    )
                    self._write_terminal_state(run_id, "failed", failed_step=index, error=error_message)
                    await self._publish(
                        run_id, automation_id, "failed", {"failed_step": index, "error": error_message}
                    )
                    return

                self._append_step_result(run_id, {"skill_id": step.skill, "status": "completed"})
                step_outputs.append(outputs)
                await self._publish(run_id, automation_id, "step_completed", {"index": index, "skill_id": step.skill})

            last_outputs = step_outputs[-1] if step_outputs else {}
            result_excerpt = ""
            for value in last_outputs.values():
                if isinstance(value, str):
                    result_excerpt = value[:500]
                    break
            audio_url = last_outputs.get("audio_url")
            await self._publish(
                run_id, automation_id, "completed", {"result_excerpt": result_excerpt, "audio_url": audio_url}
            )
            self._write_terminal_state(run_id, "completed")
        except Exception as exc:  # noqa: BLE001 - top-level guard so a run can never be stuck "running"
            error_message = f"{type(exc).__name__}: {exc}"
            self._write_terminal_state(run_id, "failed", error=error_message)
            await self._publish(run_id, automation_id, "failed", {"error": error_message})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_runner.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 145 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/automation/runner.py tests/test_automation_runner.py
git commit -m "feat(core): add AutomationRunner (fail-fast pipeline execution)"
```

---

### Task 7: Scheduler integration + app startup/shutdown wiring

**Files:**
- Create: `apps/core/core/automation/scheduler.py`
- Create: `apps/core/tests/test_automation_scheduler.py`
- Modify: `apps/core/core/app.py`
- Create: `apps/core/tests/test_automation_startup.py`

**Interfaces:**
- Consumes: `AutomationRegistry`/`LoadedAutomation` (Task 5), `AutomationRunner` (Task 6).
- Produces: `build_scheduler(automation_registry, runner) -> AsyncIOScheduler`. Modifies `create_app()`: constructs the automation registry, loads it from `settings.automations_dir`, constructs the runner, builds the scheduler, stores all three on `app.state`; adds a startup hook that marks stale `running` `AutomationRun` rows `interrupted` then starts the scheduler, and a shutdown hook that stops it.

- [ ] **Step 1: Write the failing scheduler tests**

Create `apps/core/tests/test_automation_scheduler.py`:
```python
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import AutomationRegistry, LoadedAutomation
from core.automation.runner import AutomationRunner
from core.automation.scheduler import build_scheduler
from core.skills.registry import SkillRegistry


def _valid_definition(automation_id: str, enabled: bool = True) -> AutomationDefinition:
    return AutomationDefinition(
        id=automation_id, name=automation_id, description="test", enabled=enabled,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[StepDefinition(skill="echo", inputs={})],
    )


def test_enabled_valid_automation_gets_a_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=_valid_definition("digest")
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is not None


def test_disabled_automation_gets_no_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=_valid_definition("digest", enabled=False)
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is None


def test_invalid_automation_gets_no_job():
    automation_registry = AutomationRegistry(SkillRegistry())
    automation_registry._automations["digest"] = LoadedAutomation(
        automation_id="digest", definition=None, load_error="bad cron"
    )
    runner = AutomationRunner(automation_registry, app=None)

    scheduler = build_scheduler(automation_registry, runner)

    assert scheduler.get_job("digest") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.automation.scheduler'`.

- [ ] **Step 3: Implement the scheduler wrapper**

Create `apps/core/core/automation/scheduler.py`:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.automation.registry import AutomationRegistry
from core.automation.runner import AutomationRunner


def build_scheduler(automation_registry: AutomationRegistry, runner: AutomationRunner) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for loaded in automation_registry.list():
        if not loaded.is_valid or not loaded.definition.enabled:
            continue
        scheduler.add_job(
            runner.start,
            trigger=CronTrigger.from_crontab(loaded.definition.trigger.cron),
            args=[loaded.automation_id, "cron"],
            id=loaded.automation_id,
            coalesce=True,
            misfire_grace_time=60,
            max_instances=1,
        )
    return scheduler
```

- [ ] **Step 4: Run scheduler tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_scheduler.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing app-wiring tests**

Create `apps/core/tests/test_automation_startup.py`:
```python
from fastapi.testclient import TestClient

from core.app import create_app
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import AutomationRun


def test_startup_marks_stale_running_automation_runs_as_interrupted(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("JARVIS_DATABASE_URL", db_url)

    engine = make_engine(db_url)
    init_db(engine)
    seed_session_factory = make_session_factory(engine)
    with seed_session_factory() as session:
        session.add(
            AutomationRun(run_id="stale-1", automation_id="digest", trigger="cron", status="running", steps=[])
        )
        session.commit()

    app = create_app()
    with TestClient(app):
        with app.state.session_factory() as session:
            row = session.get(AutomationRun, "stale-1")
            assert row.status == "interrupted"


def test_app_state_has_automation_components(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    assert app.state.automation_registry is not None
    assert app.state.automation_runner is not None
    assert app.state.scheduler is not None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_startup.py -v`
Expected: FAIL — `AttributeError: 'State' object has no attribute 'automation_registry'`.

- [ ] **Step 7: Wire automations into create_app()**

Read the current contents of `apps/core/core/app.py` first. Add these imports alongside the existing `core.*` imports:
```python
from core.automation.registry import AutomationRegistry
from core.automation.runner import AutomationRunner
from core.automation.scheduler import build_scheduler
from core.db.models import AutomationRun
```

(Note: `ClaudeCodeTask` is already imported from `core.db.models` — add `AutomationRun` to that same import line rather than creating a second import line for the same module.)

Then, inside `create_app()`, immediately after the existing `@app.on_event("startup")` handler for the task manager (i.e. after the closing of `_bind_task_manager_and_mark_orphans`), add:
```python
    automation_registry = AutomationRegistry(registry)
    automation_registry.load_from_directory(BASE_DIR / settings.automations_dir)
    app.state.automation_registry = automation_registry

    automation_runner = AutomationRunner(automation_registry, app)
    app.state.automation_runner = automation_runner

    scheduler = build_scheduler(automation_registry, automation_runner)
    app.state.scheduler = scheduler

    @app.on_event("startup")
    async def _start_scheduler_and_mark_orphaned_runs():
        with app.state.session_factory() as session:
            orphaned_runs = session.query(AutomationRun).filter_by(status="running").all()
            for row in orphaned_runs:
                row.status = "interrupted"
            session.commit()
        scheduler.start()

    @app.on_event("shutdown")
    async def _stop_scheduler():
        scheduler.shutdown(wait=False)
```

This is a *second* `@app.on_event("startup")` handler and the app's *first* `@app.on_event("shutdown")` handler — FastAPI supports multiple handlers per event type, so this does not replace or conflict with the existing task-manager startup hook.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_startup.py -v`
Expected: PASS (2 tests).

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 150 passed, 1 skipped (145 from Task 6, plus 3 scheduler + 2 startup).

- [ ] **Step 10: Commit**

```bash
git add core/automation/scheduler.py core/app.py tests/test_automation_scheduler.py tests/test_automation_startup.py
git commit -m "feat(core): wire AsyncIOScheduler into app startup/shutdown"
```

---

### Task 8: Backend endpoints

**Files:**
- Modify: `apps/core/core/app.py`
- Create: `apps/core/tests/test_automation_endpoints.py`

**Interfaces:**
- Consumes: `AutomationRun` (already imported from Task 7), `AutomationDefinition`/`StepDefinition`/`TriggerDefinition` (Task 2, tests only), `LoadedAutomation` (Task 5, tests only).
- Produces: `GET /automations`, `POST /automations/{automation_id}/run`, `GET /automations/runs`, `GET /automations/runs/{run_id}`.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_automation_endpoints.py`:
```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from core.app import create_app
from core.automation.definition import AutomationDefinition, StepDefinition, TriggerDefinition
from core.automation.registry import LoadedAutomation
from core.db.models import AutomationRun
from core.skills.manifest import SkillManifest
from core.skills.registry import LoadedSkill


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def _register_stub_skill(app, skill_id="echo"):
    manifest = SkillManifest(id=skill_id, name=skill_id, description="stub", input_schema={}, output_schema={})
    app.state.registry._skills[skill_id] = LoadedSkill(manifest=manifest, run=lambda inputs: {"text": "hi"})


def _register_automation(app, automation_id="digest", enabled=True):
    definition = AutomationDefinition(
        id=automation_id, name="Digest", description="test", enabled=enabled,
        trigger=TriggerDefinition(type="cron", cron="0 9 * * *"),
        steps=[StepDefinition(skill="echo", inputs={})],
    )
    app.state.automation_registry._automations[automation_id] = LoadedAutomation(
        automation_id=automation_id, definition=definition
    )


def test_list_automations_includes_registered_automation(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_automation(app)

    response = client.get("/automations")

    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert "digest" in ids


def test_list_automations_surfaces_invalid_load_error(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    app.state.automation_registry._automations["bad"] = LoadedAutomation(
        automation_id="bad", definition=None, load_error="bad cron"
    )

    response = client.get("/automations")

    entry = next(a for a in response.json() if a["id"] == "bad")
    assert entry["status"] == "invalid"
    assert entry["load_error"] == "bad cron"


def test_trigger_automation_returns_202_with_run_id(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_stub_skill(app)
    _register_automation(app)

    response = client.post("/automations/digest/run")

    assert response.status_code == 202
    assert "run_id" in response.json()


def test_trigger_unknown_automation_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post("/automations/does-not-exist/run")

    assert response.status_code == 404


def test_trigger_invalid_automation_returns_409(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    app.state.automation_registry._automations["bad"] = LoadedAutomation(
        automation_id="bad", definition=None, load_error="bad cron"
    )

    response = client.post("/automations/bad/run")

    assert response.status_code == 409


def test_trigger_disabled_automation_still_works(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _register_stub_skill(app)
    _register_automation(app, enabled=False)

    response = client.post("/automations/digest/run")

    assert response.status_code == 202


def test_list_automation_runs_returns_newest_first(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(AutomationRun(
            run_id="first", automation_id="digest", trigger="cron", status="completed", steps=[],
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        session.add(AutomationRun(
            run_id="second", automation_id="digest", trigger="cron", status="completed", steps=[],
            started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ))
        session.commit()

    response = client.get("/automations/runs")

    assert [r["run_id"] for r in response.json()] == ["second", "first"]


def test_get_automation_run_returns_404_for_unknown_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/automations/runs/does-not-exist")

    assert response.status_code == 404


def test_get_automation_run_returns_full_record(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(AutomationRun(
            run_id="abc", automation_id="digest", trigger="manual", status="failed",
            steps=[{"skill_id": "echo", "status": "failed", "error": "boom"}],
            failed_step=0, error="boom",
        ))
        session.commit()

    response = client.get("/automations/runs/abc")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_step"] == 0
    assert body["steps"] == [{"skill_id": "echo", "status": "failed", "error": "boom"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_automation_endpoints.py -v`
Expected: FAIL — 404 Not Found (routes don't exist yet).

- [ ] **Step 3: Add the endpoints**

Read the current contents of `apps/core/core/app.py` first. Add `JSONResponse` to the existing `from fastapi.responses import FileResponse` import line (making it `from fastapi.responses import FileResponse, JSONResponse`).

Add these four routes after the existing `list_tasks` route (before `@app.websocket("/ws")`):
```python
    @app.get("/automations")
    def list_automations():
        result = []
        for loaded in automation_registry.list():
            if not loaded.is_valid:
                result.append({
                    "id": loaded.automation_id,
                    "name": None,
                    "description": None,
                    "enabled": None,
                    "cron": None,
                    "status": "invalid",
                    "load_error": loaded.load_error,
                    "last_run": None,
                })
                continue

            definition = loaded.definition
            with app.state.session_factory() as session:
                last_run = (
                    session.query(AutomationRun)
                    .filter_by(automation_id=loaded.automation_id)
                    .order_by(AutomationRun.started_at.desc())
                    .first()
                )
                last_run_data = (
                    {
                        "run_id": last_run.run_id,
                        "status": last_run.status,
                        "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
                    }
                    if last_run
                    else None
                )

            result.append({
                "id": loaded.automation_id,
                "name": definition.name,
                "description": definition.description,
                "enabled": definition.enabled,
                "cron": definition.trigger.cron,
                "status": "scheduled" if definition.enabled else "disabled",
                "load_error": None,
                "last_run": last_run_data,
            })
        return result

    @app.post("/automations/{automation_id}/run")
    async def trigger_automation(automation_id: str):
        loaded = automation_registry.get(automation_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"Unknown automation: {automation_id}")
        if not loaded.is_valid:
            raise HTTPException(
                status_code=409, detail=f"Automation '{automation_id}' is invalid: {loaded.load_error}"
            )
        run_id = await automation_runner.start(automation_id, "manual")
        return JSONResponse(status_code=202, content={"run_id": run_id})

    @app.get("/automations/runs")
    def list_automation_runs(automation_id: str | None = None, limit: int = 50):
        with app.state.session_factory() as session:
            query = session.query(AutomationRun)
            if automation_id:
                query = query.filter_by(automation_id=automation_id)
            rows = query.order_by(AutomationRun.started_at.desc()).limit(limit).all()
            return [
                {
                    "run_id": row.run_id,
                    "automation_id": row.automation_id,
                    "trigger": row.trigger,
                    "status": row.status,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]

    @app.get("/automations/runs/{run_id}")
    def get_automation_run(run_id: str):
        with app.state.session_factory() as session:
            row = session.get(AutomationRun, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Automation run not found")
            return {
                "run_id": row.run_id,
                "automation_id": row.automation_id,
                "trigger": row.trigger,
                "status": row.status,
                "steps": row.steps,
                "failed_step": row.failed_step,
                "error": row.error,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_automation_endpoints.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 159 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/app.py tests/test_automation_endpoints.py
git commit -m "feat(core): add automation list/trigger/run-history endpoints"
```

---

### Task 9: The `speak` skill

**Files:**
- Create: `apps/core/skills/speak/manifest.yaml`
- Create: `apps/core/skills/speak/skill.py`
- Create: `apps/core/tests/test_speak_skill.py`

**Interfaces:**
- Consumes: `get_settings()` (`core.config`), `get_tts_provider()` (`core.providers.tts.factory`, existing M4), `tts_path()` (`core.voice.files`, existing M4).
- Produces: skill id `"speak"`, loadable via `SkillRegistry`, with `run({"text": str}) -> {"audio_url": str, "text": str}`. The `ask_digest` automation (Task 10) uses this as its second step.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_speak_skill.py`:
```python
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def test_manifest_is_not_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("speak")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_run_synthesizes_and_returns_audio_url(monkeypatch, tmp_path):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("speak")

    class FakeSettings:
        voice_dir = str(tmp_path)

    class FakeTTSProvider:
        def synthesize(self, text, output_path):
            output_path.write_bytes(b"RIFF-fake-wav-bytes")

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())
    monkeypatch.setitem(loaded.run.__globals__, "get_tts_provider", lambda settings: FakeTTSProvider())

    result = loaded.run({"text": "hello world"})

    assert result["text"] == "hello world"
    assert result["audio_url"].startswith("/voice/audio/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_speak_skill.py -v`
Expected: FAIL — `assert loaded is not None` fails (skill doesn't exist yet).

- [ ] **Step 3: Create the manifest**

Create `apps/core/skills/speak/manifest.yaml`:
```yaml
id: speak
name: Speak
description: Synthesizes the given text to speech using the configured TTS provider and returns a playable audio URL.
voice_invokable: false
input_schema:
  type: object
  properties:
    text:
      type: string
  required:
    - text
output_schema:
  type: object
  properties:
    audio_url:
      type: string
    text:
      type: string
```

- [ ] **Step 4: Create the skill implementation**

Create `apps/core/skills/speak/skill.py`:
```python
from pathlib import Path

from core.config import get_settings
from core.providers.tts.factory import get_tts_provider
from core.voice.files import tts_path

BASE_DIR = Path(__file__).resolve().parents[2]


def run(inputs: dict) -> dict:
    settings = get_settings()
    tts_provider = get_tts_provider(settings)
    voice_dir = BASE_DIR / settings.voice_dir
    output_path = tts_path(voice_dir)
    tts_provider.synthesize(inputs["text"], output_path)
    return {"audio_url": f"/voice/audio/{output_path.stem}", "text": inputs["text"]}
```

`BASE_DIR` resolves from `apps/core/skills/speak/skill.py` up 2 levels (`parents[2]`) to `apps/core` — the same `BASE_DIR` convention used in `core/app.py`. If in doubt, verify with `.venv/bin/python3 -c "from pathlib import Path; print(Path('skills/speak/skill.py').resolve().parents[2])"` from `apps/core/` — it should print the `apps/core` directory itself.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_speak_skill.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 161 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add skills/speak tests/test_speak_skill.py
git commit -m "feat(skills): add speak skill wrapping the TTS provider"
```

---

### Task 10: The `ask_digest` automation

**Files:**
- Create: `apps/core/automations/ask_digest.yaml`
- Create: `apps/core/tests/test_ask_digest_automation.py`

**Interfaces:** None new — this is the milestone's proving automation, wiring together the existing `ask` skill (M3) and the new `speak` skill (Task 9) through the full stack built in Tasks 1-8.

- [ ] **Step 1: Create the automation definition**

Create `apps/core/automations/ask_digest.yaml`:
```yaml
id: ask_digest
name: Daily Ask Digest
description: Every morning, ask the LLM for an interesting fact about today's date and speak it.
enabled: true
trigger:
  type: cron
  cron: "0 9 * * *"
steps:
  - skill: ask
    inputs:
      prompt: "In two sentences, tell me one genuinely interesting historical fact about today's date."
  - skill: speak
    inputs:
      text: "{{steps.0.response}}"
```

- [ ] **Step 2: Write the integration test**

Create `apps/core/tests/test_ask_digest_automation.py`:
```python
from core.app import create_app


def test_ask_digest_automation_loads_as_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    loaded = app.state.automation_registry.get("ask_digest")

    assert loaded is not None
    assert loaded.is_valid, loaded.load_error
    assert loaded.definition.steps[0].skill == "ask"
    assert loaded.definition.steps[1].skill == "speak"


def test_ask_digest_automation_gets_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    assert app.state.scheduler.get_job("ask_digest") is not None
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ask_digest_automation.py -v`
Expected: PASS (2 tests) — this exercises the REAL `automations/` and `skills/` directories together for the first time, confirming `ask_digest.yaml` is valid against the real `ask` and `speak` skill manifests and gets a real scheduler job.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 163 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add automations/ask_digest.yaml tests/test_ask_digest_automation.py
git commit -m "feat: add ask_digest automation (ask -> speak pipeline)"
```

---

### Task 11: End-to-End Manual Smoke Test

**Files:** None (verification only) — Steps 1 and 7 temporarily edit `apps/core/automations/ask_digest.yaml`, reverted in Step 8.

**Interfaces:** None — this task exercises the full stack built across Tasks 1-10, including real scheduled firing, which the automated suite cannot assume happens within a test's lifetime.

- [ ] **Step 1: Temporarily set the digest to fire every minute**

```bash
cd apps/core
cp automations/ask_digest.yaml /tmp/ask_digest.yaml.bak
python3 -c "
path = 'automations/ask_digest.yaml'
content = open(path).read()
content = content.replace('cron: \"0 9 * * *\"', 'cron: \"* * * * *\"')
open(path, 'w').write(content)
"
cat automations/ask_digest.yaml
```
Expected: the file now shows `cron: "* * * * *"`.

- [ ] **Step 2: Start the backend**

```bash
nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m6-smoke.log 2>&1 &
BACKEND_PID=$!
sleep 3
curl -s http://127.0.0.1:8420/automations | python3 -m json.tool
```
Expected: JSON array including `ask_digest` with `"status": "scheduled"`, `"enabled": true`, `"cron": "* * * * *"`.

- [ ] **Step 3: Manually trigger it once**

```bash
curl -s -X POST http://127.0.0.1:8420/automations/ask_digest/run | python3 -m json.tool
```
Expected: `{"run_id": "..."}`, HTTP 202.

- [ ] **Step 4: Poll the run until it finishes**

```bash
RUN_ID=<the run_id from Step 3>
sleep 8
curl -s http://127.0.0.1:8420/automations/runs/$RUN_ID | python3 -m json.tool
```
Expected: `"status": "completed"`, `"steps"` showing both `ask` and `speak` as `"status": "completed"`.

- [ ] **Step 5: Confirm the audio file was actually generated**

```bash
ls -la data/voice/tts/
```
Expected: a `.wav` file present, created within the last minute — confirms `speak`'s output actually reached the real `TTSProvider` and the real filesystem, not just a mocked path.

- [ ] **Step 6: Wait for the cron to fire on its own**

```bash
sleep 65
curl -s "http://127.0.0.1:8420/automations/runs?automation_id=ask_digest" | python3 -m json.tool
```
Expected: at least 2 runs now present for `ask_digest` — the manual one from Step 3 plus at least one with `"trigger": "cron"` — confirming the scheduler fires on its own, not just via manual trigger.

- [ ] **Step 7: Test the fail-fast render-error path**

```bash
python3 -c "
path = 'automations/ask_digest.yaml'
content = open(path).read()
content = content.replace('{{steps.0.response}}', '{{steps.0.does_not_exist}}')
open(path, 'w').write(content)
"
kill $BACKEND_PID 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
sleep 1
nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m6-smoke2.log 2>&1 &
BACKEND_PID=$!
sleep 3
curl -s -X POST http://127.0.0.1:8420/automations/ask_digest/run | python3 -m json.tool
```
Expected: still `{"run_id": "..."}` with HTTP 202 — `{{steps.0.does_not_exist}}` is a structurally valid forward-safe reference (index 0 < step 1), so it passes load-time validation; the render error only surfaces at run time, which is exactly what this step proves.

```bash
RUN_ID=<the new run_id>
sleep 8
curl -s http://127.0.0.1:8420/automations/runs/$RUN_ID | python3 -m json.tool
```
Expected: `"status": "failed"`, `"failed_step": 1`, `"error"` containing `"render_error"`.

- [ ] **Step 8: Restore the original automation file**

```bash
kill $BACKEND_PID 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
cp /tmp/ask_digest.yaml.bak automations/ask_digest.yaml
git diff automations/ask_digest.yaml
```
Expected: no diff — the file is back to its committed state.

- [ ] **Step 9: Run the full suite one final time**

```bash
.venv/bin/pytest -v
```
Expected: 163 passed, 1 skipped (the pre-existing, unrelated Piper contract skip from Milestone 4). No failures.

No commit for this task — it's verification only.
