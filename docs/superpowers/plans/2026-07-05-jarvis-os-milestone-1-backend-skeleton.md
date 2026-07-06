# Jarvis OS Milestone 1: Core Backend Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Python FastAPI backend skeleton — settings, SQLite schema, the skill manifest/registry contract, one real "echo" skill, an async event bus, and a WebSocket endpoint that streams skill-invocation events — so the skill contract (UI-callable, voice-callable-later, programmatically-callable) is proven end-to-end before any UI exists.

**Architecture:** A single FastAPI app (`core.app.create_app`) owns three collaborators built in isolation first and wired together last: a `SkillRegistry` that discovers skills from a directory of `manifest.yaml` + `skill.py` pairs, a SQLAlchemy/SQLite session factory that logs every invocation, and an `EventBus` that fans out invocation events to any connected WebSocket. `GET /skills` lists manifests, `POST /skills/{id}/invoke` runs a skill and logs + broadcasts the result, `/ws` streams events live.

**Tech Stack:** Python 3.14 (the version installed on this machine), FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2 + pydantic-settings, PyYAML, pytest + pytest-asyncio, FastAPI's `TestClient` (httpx-based) for HTTP and WebSocket tests. Dependency versions are minimum-pinned (`>=`), not exact-pinned, so pip resolves to whatever release on PyPI actually supports the installed Python version.

## Global Constraints

- macOS only — no cross-platform shims needed anywhere in this milestone.
- Backend lives at `apps/core/` inside the `jarvis-os` repo; skills live at `apps/core/skills/<skill_id>/`.
- Every subsystem the spec calls "swappable" (LLM/STT/TTS/knowledge providers) is out of scope for this milestone — only the skill contract, DB, and event bus are built now.
- Skill contract per the spec: `manifest.yaml` (`id`, `name`, `description`, `input_schema`, `output_schema`, `voice_invokable`, optional `ui_component`) + a `run(inputs: dict) -> dict` function in `skill.py`.
- `orchestrator.py` is the project's standing convention for a manual front door (`python3 orchestrator.py`) — repo root, not inside `apps/core/`.

---

### Task 1: Project Scaffolding & Settings

**Files:**
- Create: `apps/core/requirements.txt`
- Create: `apps/core/pytest.ini`
- Create: `apps/core/core/__init__.py`
- Create: `apps/core/core/config.py`
- Test: `apps/core/tests/test_config.py`

**Interfaces:**
- Produces: `core.config.Settings` (fields: `database_url: str`, `skills_dir: str`, `host: str`, `port: int`) and `core.config.get_settings() -> Settings`, env-overridable with prefix `JARVIS_`.

- [ ] **Step 1: Create the requirements file**

`apps/core/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy>=2.0.35
pydantic>=2.9
pydantic-settings>=2.5
pyyaml>=6.0
httpx>=0.27
websockets>=13.1
pytest>=8.3
pytest-asyncio>=0.24
```

- [ ] **Step 2: Create the pytest config**

`apps/core/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
```

- [ ] **Step 3: Install dependencies**

Run (from `apps/core/`): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
Expected: dependencies install with no errors.

- [ ] **Step 4: Write the failing test**

`apps/core/tests/test_config.py`:
```python
from core.config import Settings, get_settings


def test_default_settings():
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.database_url == "sqlite:///./jarvis.db"
    assert settings.port == 8420


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_PORT", "9999")
    settings = get_settings()
    assert settings.port == 9999
```

- [ ] **Step 5: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.config'` (or `core`).

- [ ] **Step 6: Create the package init and settings module**

`apps/core/core/__init__.py`: empty file.

`apps/core/core/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    database_url: str = "sqlite:///./jarvis.db"
    skills_dir: str = "skills"
    host: str = "127.0.0.1"
    port: int = 8420


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add apps/core/requirements.txt apps/core/pytest.ini apps/core/core/__init__.py apps/core/core/config.py apps/core/tests/test_config.py
git commit -m "feat(core): add project scaffolding and settings"
```

---

### Task 2: SQLite Schema & Session Factory

**Files:**
- Create: `apps/core/core/db/__init__.py`
- Create: `apps/core/core/db/models.py`
- Create: `apps/core/core/db/database.py`
- Test: `apps/core/tests/test_db.py`

**Interfaces:**
- Consumes: `core.config.get_settings` (Task 1) for the default database URL.
- Produces: `core.db.models.Base`, `core.db.models.SkillInvocation` (fields: `id`, `skill_id: str`, `inputs: dict`, `outputs: dict | None`, `status: str`, `created_at: datetime`); `core.db.database.make_engine(database_url=None)`, `make_session_factory(engine) -> sessionmaker`, `init_db(engine) -> None`.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_db.py`:
```python
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import SkillInvocation


def test_create_and_query_invocation():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        row = SkillInvocation(
            skill_id="echo",
            inputs={"text": "hello"},
            outputs={"text": "hello"},
            status="completed",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None

    with session_factory() as session:
        fetched = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert fetched.inputs == {"text": "hello"}
        assert fetched.outputs == {"text": "hello"}
        assert fetched.status == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.db'`.

- [ ] **Step 3: Write the models**

`apps/core/core/db/__init__.py`: empty file.

`apps/core/core/db/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SkillInvocation(Base):
    __tablename__ = "skill_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    outputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Write the engine/session helpers**

`apps/core/core/db/database.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.db.models import Base


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add apps/core/core/db apps/core/tests/test_db.py
git commit -m "feat(core): add SQLite schema and session factory"
```

---

### Task 3: Skill Manifest Schema & Loader

**Files:**
- Create: `apps/core/core/skills/__init__.py`
- Create: `apps/core/core/skills/manifest.py`
- Test: `apps/core/tests/test_manifest.py`

**Interfaces:**
- Produces: `core.skills.manifest.SkillManifest` (fields: `id: str`, `name: str`, `description: str`, `input_schema: dict`, `output_schema: dict`, `voice_invokable: bool`, `ui_component: str | None`), `core.skills.manifest.ManifestError`, `load_manifest(manifest_path: Path) -> SkillManifest`.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_manifest.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.skills'`.

- [ ] **Step 3: Write the manifest schema and loader**

`apps/core/core/skills/__init__.py`: empty file.

`apps/core/core/skills/manifest.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/skills/__init__.py apps/core/core/skills/manifest.py apps/core/tests/test_manifest.py
git commit -m "feat(core): add skill manifest schema and loader"
```

---

### Task 4: Skill Registry

**Files:**
- Create: `apps/core/core/skills/registry.py`
- Test: `apps/core/tests/test_registry.py`

**Interfaces:**
- Consumes: `core.skills.manifest.SkillManifest`, `load_manifest`, `ManifestError` (Task 3).
- Produces: `core.skills.registry.LoadedSkill` (fields: `manifest: SkillManifest`, `run: Callable[[dict], dict]`), `core.skills.registry.SkillRegistry` with `.load_from_directory(skills_dir: Path) -> None`, `.get(skill_id: str) -> LoadedSkill | None`, `.list() -> list[SkillManifest]`.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_registry.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'SkillRegistry'`.

- [ ] **Step 3: Write the registry**

`apps/core/core/skills/registry.py`:
```python
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.skills.manifest import ManifestError, SkillManifest, load_manifest


@dataclass
class LoadedSkill:
    manifest: SkillManifest
    run: Callable[[dict], dict]


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, LoadedSkill] = {}

    def load_from_directory(self, skills_dir: Path) -> None:
        if not skills_dir.exists():
            return
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            manifest_path = skill_dir / "manifest.yaml"
            module_path = skill_dir / "skill.py"
            if not manifest_path.exists() or not module_path.exists():
                continue
            manifest = load_manifest(manifest_path)
            run = self._load_run_function(manifest.id, module_path)
            self._skills[manifest.id] = LoadedSkill(manifest=manifest, run=run)

    @staticmethod
    def _load_run_function(skill_id: str, module_path: Path) -> Callable[[dict], dict]:
        spec = importlib.util.spec_from_file_location(f"jarvis_skill_{skill_id}", module_path)
        if spec is None or spec.loader is None:
            raise ManifestError(f"Cannot load skill module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            raise ManifestError(f"Skill '{skill_id}' has no run() function in {module_path}")
        return module.run

    def get(self, skill_id: str) -> LoadedSkill | None:
        return self._skills.get(skill_id)

    def list(self) -> list[SkillManifest]:
        return [loaded.manifest for loaded in self._skills.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/skills/registry.py apps/core/tests/test_registry.py
git commit -m "feat(core): add skill registry"
```

---

### Task 5: Real Echo Skill

**Files:**
- Create: `apps/core/skills/echo/manifest.yaml`
- Create: `apps/core/skills/echo/skill.py`
- Test: `apps/core/tests/test_echo_skill.py`

**Interfaces:**
- Consumes: `core.skills.registry.SkillRegistry` (Task 4).
- Produces: the on-disk `echo` skill at `apps/core/skills/echo/`, used by Task 7 onward as the default skill directory content.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_echo_skill.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_echo_skill.py -v`
Expected: FAIL — `assert loaded is not None` fails (`loaded` is `None`) because the skill doesn't exist yet.

- [ ] **Step 3: Write the echo skill**

`apps/core/skills/echo/manifest.yaml`:
```yaml
id: echo
name: Echo
description: Repeats back whatever text it is given. Used to prove the skill contract end-to-end.
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
    text:
      type: string
voice_invokable: true
```

`apps/core/skills/echo/skill.py`:
```python
def run(inputs: dict) -> dict:
    return {"text": inputs["text"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_echo_skill.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/skills/echo apps/core/tests/test_echo_skill.py
git commit -m "feat(skills): add echo skill"
```

---

### Task 6: Async Event Bus

**Files:**
- Create: `apps/core/core/events/__init__.py`
- Create: `apps/core/core/events/bus.py`
- Test: `apps/core/tests/test_events.py`

**Interfaces:**
- Produces: `core.events.bus.EventBus` with `.subscribe() -> asyncio.Queue`, `.unsubscribe(queue: asyncio.Queue) -> None`, `async .publish(event: dict) -> None`.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_events.py`:
```python
import asyncio

from core.events.bus import EventBus


async def test_single_subscriber_receives_event():
    bus = EventBus()
    queue = bus.subscribe()

    await bus.publish({"type": "skill_invoked", "skill_id": "echo"})

    event = await asyncio.wait_for(queue.get(), timeout=1)
    assert event == {"type": "skill_invoked", "skill_id": "echo"}


async def test_multiple_subscribers_all_receive_event():
    bus = EventBus()
    queue_a = bus.subscribe()
    queue_b = bus.subscribe()

    await bus.publish({"type": "ping"})

    assert await asyncio.wait_for(queue_a.get(), timeout=1) == {"type": "ping"}
    assert await asyncio.wait_for(queue_b.get(), timeout=1) == {"type": "ping"}


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    await bus.publish({"type": "ping"})

    assert queue.empty()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.events'`.

- [ ] **Step 3: Write the event bus**

`apps/core/core/events/__init__.py`: empty file.

`apps/core/core/events/bus.py`:
```python
import asyncio


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            await queue.put(event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_events.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/events apps/core/tests/test_events.py
git commit -m "feat(core): add async event bus"
```

---

### Task 7: FastAPI App — List Skills

**Files:**
- Create: `apps/core/core/app.py`
- Test: `apps/core/tests/test_api.py`

**Interfaces:**
- Consumes: `core.config.get_settings` (Task 1), `core.skills.registry.SkillRegistry` (Task 4), the on-disk `skills/echo` skill (Task 5).
- Produces: `core.app.create_app() -> FastAPI`, with `app.state.registry: SkillRegistry` available for later tasks.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_api.py`:
```python
from fastapi.testclient import TestClient

from core.app import create_app


def test_list_skills_includes_echo():
    app = create_app()
    client = TestClient(app)

    response = client.get("/skills")

    assert response.status_code == 200
    ids = [skill["id"] for skill in response.json()]
    assert "echo" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.app'`.

- [ ] **Step 3: Write the app factory**

`apps/core/core/app.py`:
```python
from pathlib import Path

from fastapi import FastAPI

from core.config import get_settings
from core.skills.registry import SkillRegistry

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="Jarvis OS Core")
    settings = get_settings()

    registry = SkillRegistry()
    registry.load_from_directory(BASE_DIR / settings.skills_dir)
    app.state.registry = registry

    @app.get("/skills")
    def list_skills():
        return [manifest.model_dump() for manifest in registry.list()]

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_api.py
git commit -m "feat(core): add FastAPI app with GET /skills"
```

---

### Task 8: Invoke Endpoint — Run, Log, Publish

**Files:**
- Modify: `apps/core/core/app.py`
- Modify: `apps/core/tests/test_api.py`

**Interfaces:**
- Consumes: `core.db.database.make_engine`, `make_session_factory`, `init_db`, `core.db.models.SkillInvocation` (Task 2); `core.events.bus.EventBus` (Task 6).
- Produces: `POST /skills/{skill_id}/invoke` (body `{"inputs": {...}}` → `{"outputs": {...}}`, 404 for unknown skill); `app.state.session_factory`, `app.state.event_bus`, both readable by Task 9.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `apps/core/tests/test_api.py`:
```python
from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import SkillInvocation


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_list_skills_includes_echo(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/skills")
    assert response.status_code == 200
    ids = [skill["id"] for skill in response.json()]
    assert "echo" in ids


def test_invoke_echo_skill_returns_outputs(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/skills/echo/invoke", json={"inputs": {"text": "hi"}})
    assert response.status_code == 200
    assert response.json() == {"outputs": {"text": "hi"}}


def test_invoke_echo_skill_logs_to_db(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    client.post("/skills/echo/invoke", json={"inputs": {"text": "logged"}})

    with app.state.session_factory() as session:
        row = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert row.inputs == {"text": "logged"}
        assert row.outputs == {"text": "logged"}
        assert row.status == "completed"


def test_invoke_unknown_skill_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/skills/does-not-exist/invoke", json={"inputs": {}})
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: `test_list_skills_includes_echo` PASSes; the other three FAIL with 404/`AttributeError` since the invoke route and app state don't exist yet.

- [ ] **Step 3: Update the app factory**

Replace `apps/core/core/app.py`:
```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.config import get_settings
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import SkillInvocation
from core.events.bus import EventBus
from core.skills.registry import SkillRegistry

BASE_DIR = Path(__file__).resolve().parent.parent


class InvokeRequest(BaseModel):
    inputs: dict


def create_app() -> FastAPI:
    app = FastAPI(title="Jarvis OS Core")
    settings = get_settings()

    registry = SkillRegistry()
    registry.load_from_directory(BASE_DIR / settings.skills_dir)
    app.state.registry = registry

    engine = make_engine(settings.database_url)
    init_db(engine)
    app.state.session_factory = make_session_factory(engine)

    app.state.event_bus = EventBus()

    @app.get("/skills")
    def list_skills():
        return [manifest.model_dump() for manifest in registry.list()]

    @app.post("/skills/{skill_id}/invoke")
    async def invoke_skill(skill_id: str, request: InvokeRequest):
        loaded = registry.get(skill_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")

        status = "completed"
        try:
            outputs = loaded.run(request.inputs)
        except Exception as exc:
            status = "failed"
            outputs = {"error": str(exc)}

        with app.state.session_factory() as session:
            session.add(
                SkillInvocation(
                    skill_id=skill_id,
                    inputs=request.inputs,
                    outputs=outputs,
                    status=status,
                )
            )
            session.commit()

        await app.state.event_bus.publish(
            {"type": "skill_invoked", "skill_id": skill_id, "status": status, "outputs": outputs}
        )

        if status == "failed":
            raise HTTPException(status_code=500, detail=outputs)

        return {"outputs": outputs}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_api.py
git commit -m "feat(core): add POST /skills/{id}/invoke with DB logging and event publish"
```

---

### Task 9: WebSocket Event Stream

**Files:**
- Modify: `apps/core/core/app.py`
- Modify: `apps/core/tests/test_api.py`

**Interfaces:**
- Consumes: `app.state.event_bus` (Task 8).
- Produces: `WS /ws`, streaming every published event as JSON to connected clients.

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_api.py`:
```python
def test_websocket_receives_skill_invoked_event(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    with client.websocket_connect("/ws") as websocket:
        client.post("/skills/echo/invoke", json={"inputs": {"text": "streamed"}})
        event = websocket.receive_json()

    assert event["type"] == "skill_invoked"
    assert event["skill_id"] == "echo"
    assert event["status"] == "completed"
    assert event["outputs"] == {"text": "streamed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — the `/ws` route doesn't exist (connection rejected/404).

- [ ] **Step 3: Add the WebSocket route**

In `apps/core/core/app.py`, change the import line to:
```python
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
```

Then add this route inside `create_app()`, after the `invoke_skill` route and before `return app`:
```python
    @app.websocket("/ws")
    async def events_ws(websocket: WebSocket):
        await websocket.accept()
        queue = app.state.event_bus.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            app.state.event_bus.unsubscribe(queue)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_api.py
git commit -m "feat(core): stream skill-invocation events over WebSocket"
```

---

### Task 10: Entrypoint & Manual Front Door

**Files:**
- Create: `apps/core/main.py`
- Create: `jarvis-os/orchestrator.py` (repo root)
- Test: `apps/core/tests/test_main.py`

**Interfaces:**
- Consumes: `core.app.create_app`, `core.config.get_settings` (Tasks 1, 7-9).
- Produces: a runnable server (`python3 main.py` inside `apps/core/`, or `python3 orchestrator.py` from the repo root).

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_main.py`:
```python
from fastapi import FastAPI

from main import app


def test_app_is_fastapi_instance():
    assert isinstance(app, FastAPI)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Write the entrypoint**

`apps/core/main.py`:
```python
import uvicorn

from core.app import create_app
from core.config import get_settings

app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Write the repo-root front door**

`jarvis-os/orchestrator.py`:
```python
"""Manual front door for Jarvis OS. Run: python3 orchestrator.py"""
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / "apps" / "core"


def main() -> None:
    subprocess.run([sys.executable, "main.py"], cwd=CORE_DIR, check=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full backend test suite**

Run: `.venv/bin/pytest -v` (from `apps/core/`)
Expected: all tests across every task pass (config, db, manifest, registry, echo skill, events, api, main).

- [ ] **Step 7: Manual smoke test**

Run: `cd apps/core && .venv/bin/python3 main.py`
In another terminal:
```bash
curl http://127.0.0.1:8420/skills
curl -X POST http://127.0.0.1:8420/skills/echo/invoke -H "Content-Type: application/json" -d '{"inputs": {"text": "hello"}}'
```
Expected: first command returns a JSON array containing the `echo` manifest; second returns `{"outputs":{"text":"hello"}}`. Stop the server with Ctrl+C.

- [ ] **Step 8: Commit**

```bash
git add apps/core/main.py apps/core/tests/test_main.py jarvis-os/orchestrator.py
git commit -m "feat(core): add entrypoint and orchestrator front door"
```

Note: if `orchestrator.py` is at the repo root and this git repo's root is `jarvis-os/`, drop the `jarvis-os/` prefix in the `git add` command above — use `orchestrator.py`.
