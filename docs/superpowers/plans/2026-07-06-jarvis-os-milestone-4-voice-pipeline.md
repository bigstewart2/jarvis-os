# Jarvis OS Milestone 4: Voice Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add push-to-talk voice that invokes a skill end-to-end — local STT (faster-whisper), LLM-based intent routing, skill execution, local TTS (Piper), with live progress over the existing WebSocket bus.

**Architecture:** Two new provider protocols (`STTProvider`, `TTSProvider`) following the exact M3 `LLMProvider` pattern (Protocol + concrete impl + factory + `Settings` fields), a pure-function intent router that logs every routing decision, a pipeline orchestrator implementing an "always respond, never silently fail" error policy, two new REST endpoints, and a standalone `VoiceButton` desktop component.

**Tech Stack:** Python 3.14, FastAPI (existing), `faster-whisper` (STT), `piper-tts` CLI (TTS), `jsonschema` (router input validation), `python-multipart` (file upload); React 19 + TypeScript (existing), browser Web Audio API (`getUserMedia` + `MediaRecorder`).

## Global Constraints

- Run all backend commands from `apps/core/` using `.venv/bin/python3` / `.venv/bin/pytest` — never the system Python.
- Run all frontend commands from `apps/desktop/` using `npm test` / `npm run tauri dev`.
- New Python dependencies go in `apps/core/requirements.txt` with a flexible `>=` minimum-version pin.
- Every backend task ends with a full `.venv/bin/pytest -v` run, not just the new test file.
- Every frontend task touching `apps/desktop/src` ends with a full `npm test` run.
- `STTProvider.transcribe(audio_path: Path) -> str` and `TTSProvider.synthesize(text: str, output_path: Path) -> None` are the exact Protocol signatures — every implementation and every caller must match them exactly.
- The intent router (`core/routing/intent_router.py`) is a pure function of its arguments — no I/O, no logging side effects inside it. Logging the routing decision is the caller's (pipeline's) responsibility, using the fields on the returned `RouteResult`.
- Fallback triggers, in this exact order of precedence, all producing `RouteResult(skill_id="ask", inputs={"prompt": transcript}, fallback_used=True, fallback_reason=<reason>, raw_response=<raw>)`: `"json_parse_failure"`, `"wrong_shape"`, `"model_chose_ask"`, `"unknown_skill_id"`, `"schema_validation_failure"`. No retries on any of them.
- Every pipeline stage failure past upload validation still returns HTTP 200 with a spoken-or-textual response and the `error` field populated — a hard HTTP error (400) is reserved for a missing/empty audio upload only.
- Router logging is mandatory and unconditional: every `/voice/invoke` call writes exactly one `RouteDecision` row, regardless of outcome (including cases where the LLM call itself raises and no `RouteResult` is produced — see Task 8's error handling).
- Skill modules are loaded dynamically by `core.skills.registry.SkillRegistry` and are NOT importable as `skills.<id>.skill` — tests that need to fake a skill's behavior must go through the registry (either `loaded.run.__globals__` monkeypatching for module-internal imports, or replacing the registry's stored `LoadedSkill` for the skill's `run` callable directly).

---

### Task 1: Settings extension + STTProvider/TTSProvider protocols

**Files:**
- Modify: `apps/core/core/config.py`
- Modify: `apps/core/tests/test_config.py`
- Create: `apps/core/core/providers/stt/__init__.py` (empty)
- Create: `apps/core/core/providers/stt/base.py`
- Create: `apps/core/core/providers/tts/__init__.py` (empty)
- Create: `apps/core/core/providers/tts/base.py`
- Create: `apps/core/tests/test_stt_base.py`
- Create: `apps/core/tests/test_tts_base.py`

**Interfaces:**
- Produces: `Settings.stt_provider: Literal["faster_whisper"]`, `Settings.stt_model: str`, `Settings.stt_compute_type: str`, `Settings.tts_provider: Literal["piper"]`, `Settings.piper_voice: str`, `Settings.voice_dir: str` — every later task reads these off a `Settings` instance.
- Produces: `STTProvider` Protocol — `transcribe(self, audio_path: Path) -> str`.
- Produces: `TTSProvider` Protocol — `synthesize(self, text: str, output_path: Path) -> None`.

- [ ] **Step 1: Write the failing config test**

Append to `apps/core/tests/test_config.py`:
```python
def test_voice_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.stt_provider == "faster_whisper"
    assert settings.stt_model == "small"
    assert settings.stt_compute_type == "int8"
    assert settings.tts_provider == "piper"
    assert settings.piper_voice == "en_US-lessac-medium"
    assert settings.voice_dir == "data/voice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py::test_voice_settings_defaults -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'stt_provider'`.

- [ ] **Step 3: Extend Settings**

Read the current contents of `apps/core/core/config.py` first, then add these fields to the `Settings` class (after the existing `ollama_model` field, before `def get_settings()`):
```python
    stt_provider: Literal["faster_whisper"] = "faster_whisper"
    stt_model: str = "small"
    stt_compute_type: str = "int8"
    tts_provider: Literal["piper"] = "piper"
    piper_voice: str = "en_US-lessac-medium"
    voice_dir: str = "data/voice"
```

- [ ] **Step 4: Run config test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 5: Write the failing protocol tests**

Create `apps/core/tests/test_stt_base.py`:
```python
from pathlib import Path

from core.providers.stt.base import STTProvider


class ConformingSTTProvider:
    def transcribe(self, audio_path: Path) -> str:
        return f"transcribed:{audio_path.name}"


def test_conforming_class_satisfies_protocol():
    provider: STTProvider = ConformingSTTProvider()
    assert provider.transcribe(Path("clip.wav")) == "transcribed:clip.wav"


def test_isinstance_check_against_protocol():
    provider = ConformingSTTProvider()
    assert isinstance(provider, STTProvider)
```

Create `apps/core/tests/test_tts_base.py`:
```python
from pathlib import Path

from core.providers.tts.base import TTSProvider


class ConformingTTSProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def synthesize(self, text: str, output_path: Path) -> None:
        self.calls.append((text, output_path))


def test_conforming_class_satisfies_protocol():
    provider: TTSProvider = ConformingTTSProvider()
    provider.synthesize("hello", Path("out.wav"))
    assert provider.calls == [("hello", Path("out.wav"))]


def test_isinstance_check_against_protocol():
    provider = ConformingTTSProvider()
    assert isinstance(provider, TTSProvider)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stt_base.py tests/test_tts_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.stt'` (and similarly for `tts`).

- [ ] **Step 7: Create the protocol packages**

Create `apps/core/core/providers/stt/__init__.py` (empty file).

Create `apps/core/core/providers/stt/base.py`:
```python
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    def transcribe(self, audio_path: Path) -> str:
        ...
```

Create `apps/core/core/providers/tts/__init__.py` (empty file).

Create `apps/core/core/providers/tts/base.py`:
```python
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> None:
        ...
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stt_base.py tests/test_tts_base.py -v`
Expected: PASS (2 tests each, 4 total).

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 43 passed (38 from Milestone 3, plus 5 new: 1 config + 2 STT + 2 TTS).

- [ ] **Step 10: Commit**

```bash
git add core/config.py core/providers/stt core/providers/tts tests/test_config.py tests/test_stt_base.py tests/test_tts_base.py
git commit -m "feat(core): add voice settings and STT/TTS provider protocols"
```

---

### Task 2: FasterWhisperProvider

**Files:**
- Create: `apps/core/core/providers/stt/faster_whisper_provider.py`
- Create: `apps/core/tests/test_faster_whisper_provider.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Consumes: `Settings` (Task 1) — `stt_model`, `stt_compute_type`. `STTProvider` Protocol (Task 1).
- Produces: `FasterWhisperProvider(settings: Settings)`. Later tasks (factory, Task 4) construct this directly.

- [ ] **Step 1: Add the faster-whisper dependency**

Append to `apps/core/requirements.txt`:
```
faster-whisper>=1.0
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing tests**

Create `apps/core/tests/test_faster_whisper_provider.py`:
```python
from pathlib import Path

from core.config import Settings
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    construct_count = 0

    def __init__(self, model_name: str, compute_type: str) -> None:
        FakeWhisperModel.construct_count += 1
        self.model_name = model_name
        self.compute_type = compute_type

    def transcribe(self, path: str):
        return [FakeSegment(" hello "), FakeSegment("world ")], {"language": "en"}


def _settings() -> Settings:
    return Settings(anthropic_api_key=None, stt_model="small", stt_compute_type="int8")


def test_transcribe_joins_and_strips_segments(monkeypatch):
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    result = provider.transcribe(Path("clip.wav"))

    assert result == "hello world"


def test_constructs_model_with_configured_args(monkeypatch):
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    provider.transcribe(Path("clip.wav"))

    assert provider._model.model_name == "small"
    assert provider._model.compute_type == "int8"


def test_loads_model_lazily_only_once(monkeypatch):
    FakeWhisperModel.construct_count = 0
    monkeypatch.setattr(
        "core.providers.stt.faster_whisper_provider.WhisperModel", FakeWhisperModel
    )
    provider = FasterWhisperProvider(_settings())

    assert FakeWhisperModel.construct_count == 0

    provider.transcribe(Path("clip1.wav"))
    provider.transcribe(Path("clip2.wav"))

    assert FakeWhisperModel.construct_count == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_faster_whisper_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.stt.faster_whisper_provider'`.

- [ ] **Step 4: Implement FasterWhisperProvider**

Create `apps/core/core/providers/stt/faster_whisper_provider.py`:
```python
from pathlib import Path

from faster_whisper import WhisperModel

from core.config import Settings


class FasterWhisperProvider:
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.stt_model
        self._compute_type = settings.stt_compute_type
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self._model_name, compute_type=self._compute_type)
        return self._model

    def transcribe(self, audio_path: Path) -> str:
        model = self._get_model()
        segments, _info = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments).strip()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_faster_whisper_provider.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 46 passed.

- [ ] **Step 7: Commit**

```bash
git add core/providers/stt/faster_whisper_provider.py tests/test_faster_whisper_provider.py requirements.txt
git commit -m "feat(core): add FasterWhisperProvider"
```

---

### Task 3: PiperProvider

**Files:**
- Create: `apps/core/core/providers/tts/piper_provider.py`
- Create: `apps/core/tests/test_piper_provider.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Consumes: `Settings` (Task 1) — `piper_voice`. `TTSProvider` Protocol (Task 1).
- Produces: `PiperProvider(settings: Settings)`, `PiperTTSError`. Later tasks (factory, Task 4) construct `PiperProvider` directly.

- [ ] **Step 1: Add the piper-tts dependency**

Append to `apps/core/requirements.txt`:
```
piper-tts>=1.2
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing tests**

Create `apps/core/tests/test_piper_provider.py`:
```python
from unittest.mock import Mock

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import PiperProvider, PiperTTSError


def _settings() -> Settings:
    return Settings(anthropic_api_key=None, piper_voice="en_US-lessac-medium")


def test_synthesize_calls_piper_with_correct_args(monkeypatch, tmp_path):
    captured = {}

    def fake_run(args, input, text, capture_output):
        captured["args"] = args
        captured["input"] = input
        return Mock(returncode=0, stderr="")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings())
    output_path = tmp_path / "out.wav"

    provider.synthesize("hello world", output_path)

    assert captured["args"] == [
        "piper",
        "--model",
        "en_US-lessac-medium",
        "--output_file",
        str(output_path),
    ]
    assert captured["input"] == "hello world"


def test_synthesize_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(args, input, text, capture_output):
        return Mock(returncode=1, stderr="model not found")

    monkeypatch.setattr("core.providers.tts.piper_provider.subprocess.run", fake_run)
    provider = PiperProvider(_settings())

    with pytest.raises(PiperTTSError, match="model not found"):
        provider.synthesize("hello", tmp_path / "out.wav")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_piper_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.tts.piper_provider'`.

- [ ] **Step 4: Implement PiperProvider**

Create `apps/core/core/providers/tts/piper_provider.py`:
```python
import subprocess
from pathlib import Path

from core.config import Settings


class PiperTTSError(Exception):
    pass


class PiperProvider:
    def __init__(self, settings: Settings) -> None:
        self._voice = settings.piper_voice

    def synthesize(self, text: str, output_path: Path) -> None:
        result = subprocess.run(
            ["piper", "--model", self._voice, "--output_file", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise PiperTTSError(f"piper exited with {result.returncode}: {result.stderr}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_piper_provider.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 48 passed.

- [ ] **Step 7: Commit**

```bash
git add core/providers/tts/piper_provider.py tests/test_piper_provider.py requirements.txt
git commit -m "feat(core): add PiperProvider"
```

---

### Task 4: STT/TTS factories + app.state wiring

**Files:**
- Create: `apps/core/core/providers/stt/factory.py`
- Create: `apps/core/core/providers/tts/factory.py`
- Create: `apps/core/tests/test_stt_factory.py`
- Create: `apps/core/tests/test_tts_factory.py`
- Modify: `apps/core/core/app.py`
- Modify: `apps/core/tests/test_api.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `FasterWhisperProvider` (Task 2), `PiperProvider` (Task 3).
- Produces: `get_stt_provider(settings) -> STTProvider`, `get_tts_provider(settings) -> TTSProvider`. `app.state.stt_provider` and `app.state.tts_provider`, constructed once at startup — later tasks (the pipeline, Task 8) read these off `app.state` rather than calling the factories themselves.

- [ ] **Step 1: Write the failing factory tests**

Create `apps/core/tests/test_stt_factory.py`:
```python
from core.config import Settings
from core.providers.stt.factory import get_stt_provider
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


def test_returns_faster_whisper_provider():
    settings = Settings(anthropic_api_key=None, stt_provider="faster_whisper")
    provider = get_stt_provider(settings)
    assert isinstance(provider, FasterWhisperProvider)
```

Create `apps/core/tests/test_tts_factory.py`:
```python
from core.config import Settings
from core.providers.tts.factory import get_tts_provider
from core.providers.tts.piper_provider import PiperProvider


def test_returns_piper_provider():
    settings = Settings(anthropic_api_key=None, tts_provider="piper")
    provider = get_tts_provider(settings)
    assert isinstance(provider, PiperProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stt_factory.py tests/test_tts_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.stt.factory'` (and similarly for `tts`).

- [ ] **Step 3: Implement the factories**

Create `apps/core/core/providers/stt/factory.py`:
```python
from core.config import Settings
from core.providers.stt.base import STTProvider
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider


def get_stt_provider(settings: Settings) -> STTProvider:
    if settings.stt_provider == "faster_whisper":
        return FasterWhisperProvider(settings)
    raise ValueError(f"Unknown stt_provider: {settings.stt_provider}")
```

Create `apps/core/core/providers/tts/factory.py`:
```python
from core.config import Settings
from core.providers.tts.base import TTSProvider
from core.providers.tts.piper_provider import PiperProvider


def get_tts_provider(settings: Settings) -> TTSProvider:
    if settings.tts_provider == "piper":
        return PiperProvider(settings)
    raise ValueError(f"Unknown tts_provider: {settings.tts_provider}")
```

- [ ] **Step 4: Run factory tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stt_factory.py tests/test_tts_factory.py -v`
Expected: PASS (1 test each).

- [ ] **Step 5: Write the failing app-state wiring test**

Append to `apps/core/tests/test_api.py` (it already has the `_client(tmp_path, monkeypatch)` helper):
```python
def test_app_state_has_stt_and_tts_providers(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert app.state.stt_provider is not None
    assert app.state.tts_provider is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py::test_app_state_has_stt_and_tts_providers -v`
Expected: FAIL — `AttributeError` (no `stt_provider` on `app.state`).

- [ ] **Step 7: Wire the providers into create_app()**

Read the current contents of `apps/core/core/app.py` first. Add these two imports alongside the existing `core.*` imports:
```python
from core.providers.stt.factory import get_stt_provider
from core.providers.tts.factory import get_tts_provider
```

Then, inside `create_app()`, immediately after the line `app.state.event_bus = EventBus()`, add:
```python
    app.state.stt_provider = get_stt_provider(settings)
    app.state.tts_provider = get_tts_provider(settings)
```

`FasterWhisperProvider.__init__` does not load the model eagerly (Task 2's lazy-loading design), so this is safe to run on every `create_app()` call, including in every existing test that constructs the app — it will not slow down the test suite or require the model to be downloaded.

- [ ] **Step 8: Run the wiring test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py::test_app_state_has_stt_and_tts_providers -v`
Expected: PASS.

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 51 passed.

- [ ] **Step 10: Commit**

```bash
git add core/providers/stt/factory.py core/providers/tts/factory.py core/app.py tests/test_stt_factory.py tests/test_tts_factory.py tests/test_api.py
git commit -m "feat(core): add STT/TTS provider factories and wire them into app startup"
```

---

### Task 5: Shared skill-invocation helper (refactor)

**Files:**
- Create: `apps/core/core/skills/invocation.py`
- Create: `apps/core/tests/test_skill_invocation.py`
- Modify: `apps/core/core/app.py`

**Interfaces:**
- Consumes: `SkillRegistry` (existing, M1), `SkillInvocation` DB model (existing, M1), `EventBus` (existing, M1).
- Produces: `SkillNotFoundError`, `async def invoke_and_record_skill(app: FastAPI, skill_id: str, inputs: dict) -> tuple[str, dict]` — returns `(status, outputs)` where `status` is `"completed"` or `"failed"`; raises `SkillNotFoundError` if `skill_id` isn't registered. The voice pipeline (Task 8) and the existing `POST /skills/{id}/invoke` route both call this — it is the single place skill invocation, DB logging, and event publishing happen, so the two callers cannot drift.

This task is a pure refactor: `POST /skills/{id}/invoke`'s existing behavior must not change. Its existing tests in `tests/test_api.py` are the regression guard — they must all still pass unchanged after this refactor.

- [ ] **Step 1: Write the failing tests for the extracted function**

Create `apps/core/tests/test_skill_invocation.py`:
```python
import asyncio

import pytest

from core.app import create_app
from core.db.models import SkillInvocation
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill


def test_invoke_and_record_skill_returns_completed_status_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    status, outputs = asyncio.run(invoke_and_record_skill(app, "echo", {"text": "hi"}))

    assert status == "completed"
    assert outputs == {"text": "hi"}

    with app.state.session_factory() as session:
        row = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert row.status == "completed"
        assert row.outputs == {"text": "hi"}


def test_invoke_and_record_skill_raises_for_unknown_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    with pytest.raises(SkillNotFoundError):
        asyncio.run(invoke_and_record_skill(app, "does-not-exist", {}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_skill_invocation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.skills.invocation'`.

- [ ] **Step 3: Extract the helper**

Create `apps/core/core/skills/invocation.py`:
```python
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from core.db.models import SkillInvocation


class SkillNotFoundError(Exception):
    pass


async def invoke_and_record_skill(app: FastAPI, skill_id: str, inputs: dict) -> tuple[str, dict]:
    loaded = app.state.registry.get(skill_id)
    if loaded is None:
        raise SkillNotFoundError(skill_id)

    status = "completed"
    try:
        outputs = await run_in_threadpool(loaded.run, inputs)
    except Exception as exc:
        status = "failed"
        outputs = {"error": str(exc)}

    with app.state.session_factory() as session:
        session.add(
            SkillInvocation(skill_id=skill_id, inputs=inputs, outputs=outputs, status=status)
        )
        session.commit()

    await app.state.event_bus.publish(
        {"type": "skill_invoked", "skill_id": skill_id, "status": status, "outputs": outputs}
    )
    return status, outputs
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/test_skill_invocation.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Update the route to use the extracted helper**

Read the current contents of `apps/core/core/app.py` first. Replace this import block:
```python
from core.db.models import SkillInvocation
```
with:
```python
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill
```
(Remove the now-unused `from fastapi.concurrency import run_in_threadpool` import too — it moved into `invocation.py` — but keep it if a later task in this same file still needs it; check the full file before removing.)

Replace the entire body of `invoke_skill`:
```python
    @app.post("/skills/{skill_id}/invoke")
    async def invoke_skill(skill_id: str, request: InvokeRequest):
        loaded = registry.get(skill_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")

        status = "completed"
        try:
            outputs = await run_in_threadpool(loaded.run, request.inputs)
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
```
with:
```python
    @app.post("/skills/{skill_id}/invoke")
    async def invoke_skill(skill_id: str, request: InvokeRequest):
        try:
            status, outputs = await invoke_and_record_skill(app, skill_id, request.inputs)
        except SkillNotFoundError:
            raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")

        if status == "failed":
            raise HTTPException(status_code=500, detail=outputs)

        return {"outputs": outputs}
```

- [ ] **Step 6: Run the full suite to confirm no regression**

Run: `.venv/bin/pytest -v`
Expected: 53 passed (51 from Task 4, plus the 2 new tests from this task) — all pre-existing `test_api.py` tests for `/skills/{id}/invoke` (200, 404, 500, DB logging, WebSocket event) must still pass unchanged.

- [ ] **Step 7: Commit**

```bash
git add core/skills/invocation.py core/app.py tests/test_skill_invocation.py
git commit -m "refactor(core): extract shared skill-invocation helper"
```

---

### Task 6: Intent router

**Files:**
- Create: `apps/core/core/routing/__init__.py` (empty)
- Create: `apps/core/core/routing/intent_router.py`
- Create: `apps/core/tests/test_intent_router.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Consumes: `LLMProvider` Protocol (M3), `SkillManifest` (M1).
- Produces: `RouteResult` dataclass (`skill_id: str`, `inputs: dict`, `fallback_used: bool`, `fallback_reason: str | None`, `raw_response: str`), `route(transcript: str, manifests: list[SkillManifest], llm: LLMProvider) -> RouteResult`. The voice pipeline (Task 8) calls this directly and reads every field of the returned `RouteResult`.

- [ ] **Step 1: Add the jsonschema dependency**

Append to `apps/core/requirements.txt`:
```
jsonschema>=4.23
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing tests**

Create `apps/core/tests/test_intent_router.py`:
```python
import pytest

from core.routing.intent_router import RouteResult, route
from core.skills.manifest import SkillManifest


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.last_prompt = prompt
        self.last_system = system
        return self.response


ECHO_MANIFEST = SkillManifest(
    id="echo",
    name="Echo",
    description="Repeats back text",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    voice_invokable=True,
)

ASK_MANIFEST = SkillManifest(
    id="ask",
    name="Ask",
    description="General question answering",
    input_schema={
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    },
    output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
    voice_invokable=True,
)

MANIFESTS = [ECHO_MANIFEST, ASK_MANIFEST]


def test_routes_to_matching_skill():
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"text": "hello"}}')

    result = route("say hello", MANIFESTS, llm)

    assert result == RouteResult(
        skill_id="echo",
        inputs={"text": "hello"},
        fallback_used=False,
        fallback_reason=None,
        raw_response=llm.response,
    )


def test_strips_json_code_fence():
    llm = FakeLLM('```json\n{"skill_id": "echo", "inputs": {"text": "hi"}}\n```')

    result = route("say hi", MANIFESTS, llm)

    assert result.skill_id == "echo"
    assert result.fallback_used is False


def test_falls_back_on_json_parse_failure():
    llm = FakeLLM("not json at all")

    result = route("garble garble", MANIFESTS, llm)

    assert result.skill_id == "ask"
    assert result.fallback_used is True
    assert result.fallback_reason == "json_parse_failure"
    assert result.inputs == {"prompt": "garble garble"}


def test_falls_back_on_wrong_shape():
    llm = FakeLLM('{"skill_id": "echo"}')

    result = route("say hello", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "wrong_shape"


def test_falls_back_on_unknown_skill_id():
    llm = FakeLLM('{"skill_id": "does-not-exist", "inputs": {}}')

    result = route("do something", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "unknown_skill_id"


def test_falls_back_on_schema_validation_failure():
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"wrong_field": "x"}}')

    result = route("say hello", MANIFESTS, llm)

    assert result.fallback_used is True
    assert result.fallback_reason == "schema_validation_failure"


def test_falls_back_when_model_chooses_ask():
    llm = FakeLLM('{"skill_id": "ask", "inputs": {"prompt": "what is 2 plus 2"}}')

    result = route("what is 2 plus 2", MANIFESTS, llm)

    assert result.skill_id == "ask"
    assert result.fallback_used is True
    assert result.fallback_reason == "model_chose_ask"


def test_llm_exception_propagates():
    class RaisingLLM:
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        route("hello", MANIFESTS, RaisingLLM())


def test_only_voice_invokable_manifests_sent_to_llm():
    hidden = SkillManifest(
        id="hidden",
        name="Hidden",
        description="not voice invokable",
        input_schema={},
        output_schema={},
        voice_invokable=False,
    )
    llm = FakeLLM('{"skill_id": "echo", "inputs": {"text": "hi"}}')

    route("say hi", [ECHO_MANIFEST, ASK_MANIFEST, hidden], llm)

    assert "hidden" not in llm.last_prompt
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_intent_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.routing'`.

- [ ] **Step 4: Implement the intent router**

Create `apps/core/core/routing/__init__.py` (empty file).

Create `apps/core/core/routing/intent_router.py`:
```python
import json
from dataclasses import dataclass

import jsonschema

from core.providers.llm.base import LLMProvider
from core.skills.manifest import SkillManifest

ROUTER_SYSTEM_PROMPT = (
    "You route a user's spoken request to one skill. You will receive the "
    "transcript and a list of available skills with their input schemas. "
    "Respond with ONLY a JSON object, no markdown, no explanation: "
    '{"skill_id": "<id>", "inputs": {<inputs matching that skill\'s input_schema>}}. '
    "If no skill clearly matches the request, or you are not confident, choose "
    '{"skill_id": "ask", "inputs": {"prompt": "<the transcript, verbatim>"}}.'
)


@dataclass
class RouteResult:
    skill_id: str
    inputs: dict
    fallback_used: bool
    fallback_reason: str | None
    raw_response: str


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _build_user_prompt(transcript: str, manifests: list[SkillManifest]) -> str:
    skills_payload = [
        {"id": m.id, "description": m.description, "input_schema": m.input_schema}
        for m in manifests
    ]
    return f"{transcript}\n\n{json.dumps(skills_payload)}"


def route(transcript: str, manifests: list[SkillManifest], llm: LLMProvider) -> RouteResult:
    voice_manifests = [m for m in manifests if m.voice_invokable]
    by_id = {m.id: m for m in voice_manifests}

    raw = llm.complete(_build_user_prompt(transcript, voice_manifests), system=ROUTER_SYSTEM_PROMPT)

    def fallback(reason: str) -> RouteResult:
        return RouteResult(
            skill_id="ask",
            inputs={"prompt": transcript},
            fallback_used=True,
            fallback_reason=reason,
            raw_response=raw,
        )

    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return fallback("json_parse_failure")

    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("skill_id"), str)
        or not isinstance(parsed.get("inputs"), dict)
    ):
        return fallback("wrong_shape")

    skill_id = parsed["skill_id"]
    inputs = parsed["inputs"]

    if skill_id == "ask":
        return fallback("model_chose_ask")

    manifest = by_id.get(skill_id)
    if manifest is None:
        return fallback("unknown_skill_id")

    try:
        jsonschema.validate(inputs, manifest.input_schema)
    except jsonschema.ValidationError:
        return fallback("schema_validation_failure")

    return RouteResult(
        skill_id=skill_id,
        inputs=inputs,
        fallback_used=False,
        fallback_reason=None,
        raw_response=raw,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_intent_router.py -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 62 passed.

- [ ] **Step 7: Commit**

```bash
git add core/routing tests/test_intent_router.py requirements.txt
git commit -m "feat(core): add LLM-based intent router"
```

---

### Task 7: Voice file lifecycle

**Files:**
- Create: `apps/core/core/voice/__init__.py` (empty)
- Create: `apps/core/core/voice/files.py`
- Create: `apps/core/tests/test_voice_files.py`

**Interfaces:**
- Produces: `upload_path(voice_dir: Path, extension: str = "webm") -> Path`, `tts_path(voice_dir: Path) -> Path`, `prune_tts_files(voice_dir: Path, max_age_seconds: float = 3600.0, keep_newest: int = 20) -> None`, `clear_voice_dir(voice_dir: Path) -> None`. The voice pipeline (Task 8) calls all four.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_voice_files.py`:
```python
import os
import time

from core.voice.files import clear_voice_dir, prune_tts_files, tts_path, upload_path


def test_upload_path_creates_uploads_dir_and_unique_names(tmp_path):
    voice_dir = tmp_path / "voice"

    path1 = upload_path(voice_dir)
    path2 = upload_path(voice_dir)

    assert path1.parent == voice_dir / "uploads"
    assert path1.parent.exists()
    assert path1 != path2
    assert path1.suffix == ".webm"


def test_tts_path_creates_tts_dir_with_wav_extension(tmp_path):
    voice_dir = tmp_path / "voice"

    path = tts_path(voice_dir)

    assert path.parent == voice_dir / "tts"
    assert path.suffix == ".wav"


def test_prune_tts_files_keeps_newest_n_regardless_of_age(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    for i in range(5):
        (tts_dir / f"{i}.wav").write_text("x")

    prune_tts_files(voice_dir, max_age_seconds=0, keep_newest=3)

    remaining = list(tts_dir.iterdir())
    assert len(remaining) == 3


def test_prune_tts_files_deletes_old_files_beyond_keep_newest(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    old_file = tts_dir / "old.wav"
    old_file.write_text("x")
    old_time = time.time() - 7200
    os.utime(old_file, (old_time, old_time))

    prune_tts_files(voice_dir, max_age_seconds=3600, keep_newest=0)

    assert not old_file.exists()


def test_prune_tts_files_keeps_recent_files_even_beyond_keep_newest(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    recent_file = tts_dir / "recent.wav"
    recent_file.write_text("x")

    prune_tts_files(voice_dir, max_age_seconds=3600, keep_newest=0)

    assert recent_file.exists()


def test_clear_voice_dir_removes_all_contents(tmp_path):
    voice_dir = tmp_path / "voice"
    (voice_dir / "uploads").mkdir(parents=True)
    (voice_dir / "uploads" / "stale.webm").write_text("x")

    clear_voice_dir(voice_dir)

    assert voice_dir.exists()
    assert list(voice_dir.iterdir()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_voice_files.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.voice'`.

- [ ] **Step 3: Implement the file lifecycle helpers**

Create `apps/core/core/voice/__init__.py` (empty file).

Create `apps/core/core/voice/files.py`:
```python
import shutil
import time
import uuid
from pathlib import Path


def upload_path(voice_dir: Path, extension: str = "webm") -> Path:
    uploads_dir = voice_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir / f"{uuid.uuid4()}.{extension}"


def tts_path(voice_dir: Path) -> Path:
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    return tts_dir / f"{uuid.uuid4()}.wav"


def prune_tts_files(voice_dir: Path, max_age_seconds: float = 3600.0, keep_newest: int = 20) -> None:
    tts_dir = voice_dir / "tts"
    if not tts_dir.exists():
        return
    files = sorted(tts_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    now = time.time()
    for index, path in enumerate(files):
        if index < keep_newest:
            continue
        if now - path.stat().st_mtime > max_age_seconds:
            path.unlink()


def clear_voice_dir(voice_dir: Path) -> None:
    if voice_dir.exists():
        shutil.rmtree(voice_dir)
    voice_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_voice_files.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 68 passed.

- [ ] **Step 6: Commit**

```bash
git add core/voice/__init__.py core/voice/files.py tests/test_voice_files.py
git commit -m "feat(core): add voice file lifecycle helpers"
```

---

### Task 8: RouteDecision model + voice pipeline orchestration

**Files:**
- Modify: `apps/core/core/db/models.py`
- Create: `apps/core/core/voice/pipeline.py`
- Create: `apps/core/tests/test_voice_pipeline.py`

**Interfaces:**
- Consumes: `get_llm_provider` (M3 factory), `route`/`RouteResult` (Task 6), `upload_path`/`tts_path`/`prune_tts_files` (Task 7), `invoke_and_record_skill`/`SkillNotFoundError` (Task 5), `get_settings` (M1). Reads `app.state.stt_provider`, `app.state.tts_provider`, `app.state.registry`, `app.state.session_factory`, `app.state.event_bus`.
- Produces: `RouteDecision` DB model. `async def run_voice_pipeline(app: FastAPI, audio_bytes: bytes, upload_extension: str) -> dict` returning exactly the response shape below — the `POST /voice/invoke` endpoint (Task 9) returns this dict directly as its JSON response.

Response shape (every key always present):
```python
{
    "invocation_id": str,
    "transcript": str,
    "skill_id": str | None,
    "fallback_used": bool,
    "fallback_reason": str | None,
    "outputs": dict | None,
    "response_text": str,
    "audio_url": str | None,
    "error": str | None,
}
```

- [ ] **Step 1: Write the failing DB model test**

Read the current contents of `apps/core/core/db/models.py` first. Then append this test to `apps/core/tests/test_db.py` (check the file first for its existing helper pattern — it likely constructs an in-memory engine; match that pattern):
```python
def test_route_decision_can_be_created_and_queried(session_factory):
    from core.db.models import RouteDecision

    with session_factory() as session:
        session.add(
            RouteDecision(
                transcript="what time is it",
                raw_response='{"skill_id": "ask", "inputs": {}}',
                skill_id="ask",
                fallback_used=True,
                fallback_reason="model_chose_ask",
            )
        )
        session.commit()

    with session_factory() as session:
        row = session.query(RouteDecision).one()
        assert row.transcript == "what time is it"
        assert row.skill_id == "ask"
        assert row.fallback_used is True
        assert row.fallback_reason == "model_chose_ask"
        assert row.created_at is not None
```

If `tests/test_db.py` does not already have a `session_factory` fixture, adapt this test to match whatever pattern the existing tests in that file use for constructing an engine/session (e.g. `make_engine("sqlite:///:memory:")` + `init_db(engine)` + `make_session_factory(engine)`) rather than introducing a new fixture — read the file first and mirror it exactly.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -v -k route_decision`
Expected: FAIL — `ImportError: cannot import name 'RouteDecision'`.

- [ ] **Step 3: Add the RouteDecision model**

Add this class to `apps/core/core/db/models.py`, after the existing `SkillInvocation` class. First add `Boolean` to the existing `from sqlalchemy import ...` line (alongside `DateTime, Integer, JSON, String`):
```python
class RouteDecision(Base):
    __tablename__ = "route_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transcript: Mapped[str] = mapped_column(String, nullable=False)
    raw_response: Mapped[str] = mapped_column(String, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Run the DB test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 5: Write the failing pipeline tests**

Create `apps/core/tests/test_voice_pipeline.py`:
```python
import asyncio

from core.app import create_app
from core.db.models import RouteDecision
from core.skills.registry import LoadedSkill
from core.voice.pipeline import run_voice_pipeline


class FakeSTT:
    def __init__(self, transcript: str = "what is two plus two", raise_exc: Exception | None = None):
        self.transcript = transcript
        self.raise_exc = raise_exc

    def transcribe(self, audio_path):
        if self.raise_exc:
            raise self.raise_exc
        return self.transcript


class FakeTTS:
    def __init__(self, raise_exc: Exception | None = None):
        self.raise_exc = raise_exc
        self.calls: list[str] = []

    def synthesize(self, text, output_path):
        self.calls.append(text)
        if self.raise_exc:
            raise self.raise_exc
        output_path.write_bytes(b"RIFF-fake-wav-bytes")


class FakeRouterLLM:
    def __init__(self, response: str):
        self.response = response

    def complete(self, prompt, *, system=None):
        return self.response


class RaisingLLM:
    def complete(self, prompt, *, system=None):
        raise RuntimeError("provider down")


def _make_app(
    tmp_path,
    monkeypatch,
    stt=None,
    tts=None,
    llm_response='{"skill_id": "echo", "inputs": {"text": "hi"}}',
):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice"))
    app = create_app()
    app.state.stt_provider = stt or FakeSTT()
    app.state.tts_provider = tts or FakeTTS()
    monkeypatch.setattr(
        "core.voice.pipeline.get_llm_provider", lambda settings: FakeRouterLLM(llm_response)
    )
    return app


def test_happy_path_invokes_skill_and_returns_full_result(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["transcript"] == "what is two plus two"
    assert result["skill_id"] == "echo"
    assert result["fallback_used"] is False
    assert result["outputs"] == {"text": "hi"}
    assert result["response_text"] == "hi"
    assert result["error"] is None
    assert result["audio_url"] is not None


def test_empty_transcript_skips_routing_and_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, stt=FakeSTT(transcript="   "))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["transcript"] == ""
    assert result["skill_id"] is None
    assert result["error"] == "empty_transcript"
    assert result["response_text"] == "I didn't catch that."


def test_stt_failure_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, stt=FakeSTT(raise_exc=RuntimeError("bad audio")))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "I couldn't process that audio."
    assert "stt_failed" in result["error"]


def test_llm_failure_during_routing_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    monkeypatch.setattr("core.voice.pipeline.get_llm_provider", lambda settings: RaisingLLM())

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "I couldn't reach the language model."
    assert "routing_failed" in result["error"]


def test_skill_failure_returns_degraded_response(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    original = app.state.registry.get("echo")

    def failing_run(inputs):
        raise RuntimeError("echo blew up")

    app.state.registry._skills["echo"] = LoadedSkill(manifest=original.manifest, run=failing_run)

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["response_text"] == "The echo skill failed."
    assert "skill_failed" in result["error"]


def test_tts_failure_still_returns_full_result_without_audio(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, tts=FakeTTS(raise_exc=RuntimeError("piper missing")))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["skill_id"] == "echo"
    assert result["outputs"] == {"text": "hi"}
    assert result["audio_url"] is None
    assert "tts_failed" in result["error"]


def test_fallback_route_invokes_ask_and_logs_route_decision(tmp_path, monkeypatch):
    app = _make_app(
        tmp_path,
        monkeypatch,
        llm_response='{"skill_id": "ask", "inputs": {"prompt": "what is two plus two"}}',
    )
    # The ask skill's own run() imports get_llm_provider independently (it's a
    # dynamically-loaded skill module, not core.voice.pipeline) — monkeypatching
    # core.voice.pipeline.get_llm_provider only fakes the ROUTER's LLM call, not
    # ask's own answer-generation call. Fake that separately via __globals__,
    # same technique used in Milestone 3's test_ask_skill.py.
    ask_loaded = app.state.registry.get("ask")
    monkeypatch.setitem(ask_loaded.run.__globals__, "get_llm_provider", lambda settings: FakeRouterLLM("4"))

    result = asyncio.run(run_voice_pipeline(app, b"fake-audio-bytes", "webm"))

    assert result["skill_id"] == "ask"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "model_chose_ask"
    assert result["outputs"] == {"response": "4"}

    with app.state.session_factory() as session:
        rows = session.query(RouteDecision).all()
        assert len(rows) == 1
        assert rows[0].fallback_used is True
        assert rows[0].fallback_reason == "model_chose_ask"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_voice_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.voice.pipeline'`.

- [ ] **Step 7: Implement the pipeline**

Create `apps/core/core/voice/pipeline.py`:
```python
import uuid
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from core.config import Settings, get_settings
from core.db.models import RouteDecision
from core.providers.llm.factory import get_llm_provider
from core.routing.intent_router import route
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill
from core.voice.files import prune_tts_files, tts_path, upload_path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _log_route_decision(
    app, transcript: str, skill_id: str, raw_response: str, fallback_used: bool, fallback_reason: str | None
) -> None:
    with app.state.session_factory() as session:
        session.add(
            RouteDecision(
                transcript=transcript,
                raw_response=raw_response,
                skill_id=skill_id,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )
        )
        session.commit()


def _derive_response_text(outputs: dict, skill_id: str) -> str:
    response = outputs.get("response")
    if isinstance(response, str):
        return response
    for value in outputs.values():
        if isinstance(value, str):
            return value
    return f"Done — {skill_id} completed."


async def _publish(app, invocation_id: str, stage: str, detail: dict) -> None:
    await app.state.event_bus.publish(
        {"type": "voice_status", "invocation_id": invocation_id, "stage": stage, "detail": detail}
    )


async def run_voice_pipeline(app, audio_bytes: bytes, upload_extension: str) -> dict:
    settings: Settings = get_settings()
    invocation_id = str(uuid.uuid4())
    voice_dir = BASE_DIR / settings.voice_dir
    prune_tts_files(voice_dir)

    result = {
        "invocation_id": invocation_id,
        "transcript": "",
        "skill_id": None,
        "fallback_used": False,
        "fallback_reason": None,
        "outputs": None,
        "response_text": "",
        "audio_url": None,
        "error": None,
    }

    async def _speak_and_finish(text: str, error: str | None) -> dict:
        result["response_text"] = text
        result["error"] = error
        try:
            output_path = tts_path(voice_dir)
            await run_in_threadpool(app.state.tts_provider.synthesize, text, output_path)
            result["audio_url"] = f"/voice/audio/{output_path.stem}"
        except Exception as exc:
            tts_error = f"tts_failed: {exc}"
            result["error"] = f"{error}; {tts_error}" if error else tts_error
        stage = "error" if result["error"] else "done"
        await _publish(app, invocation_id, stage, {"message": result["error"]} if result["error"] else {})
        return result

    upload = upload_path(voice_dir, extension=upload_extension)
    upload.write_bytes(audio_bytes)

    await _publish(app, invocation_id, "transcribing", {})
    try:
        transcript = await run_in_threadpool(app.state.stt_provider.transcribe, upload)
    except Exception as exc:
        upload.unlink(missing_ok=True)
        return await _speak_and_finish("I couldn't process that audio.", f"stt_failed: {exc}")
    upload.unlink(missing_ok=True)

    result["transcript"] = transcript
    if not transcript.strip():
        return await _speak_and_finish("I didn't catch that.", "empty_transcript")

    await _publish(app, invocation_id, "routing", {"transcript": transcript})
    manifests = app.state.registry.list()
    llm = get_llm_provider(settings)
    try:
        route_result = await run_in_threadpool(route, transcript, manifests, llm)
    except Exception as exc:
        return await _speak_and_finish("I couldn't reach the language model.", f"routing_failed: {exc}")

    _log_route_decision(
        app,
        transcript,
        route_result.skill_id,
        route_result.raw_response,
        route_result.fallback_used,
        route_result.fallback_reason,
    )
    result["skill_id"] = route_result.skill_id
    result["fallback_used"] = route_result.fallback_used
    result["fallback_reason"] = route_result.fallback_reason

    await _publish(
        app,
        invocation_id,
        "invoking_skill",
        {"skill_id": route_result.skill_id, "fallback_used": route_result.fallback_used},
    )
    try:
        status, outputs = await invoke_and_record_skill(app, route_result.skill_id, route_result.inputs)
    except SkillNotFoundError:
        # route() already validates skill_id against the registry at routing time;
        # this branch only guards a concurrent-registry-change race that cannot
        # happen in this single-process app, but keeps the pipeline's always-respond
        # guarantee true even in that theoretical case.
        return await _speak_and_finish(
            "Something went wrong routing your request.",
            f"route_skill_missing: {route_result.skill_id}",
        )
    result["outputs"] = outputs

    if status == "failed":
        return await _speak_and_finish(
            f"The {route_result.skill_id} skill failed.", f"skill_failed: {outputs.get('error')}"
        )

    await _publish(app, invocation_id, "synthesizing", {"skill_id": route_result.skill_id})
    response_text = _derive_response_text(outputs, route_result.skill_id)
    return await _speak_and_finish(response_text, None)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_voice_pipeline.py -v`
Expected: PASS (7 tests).

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 75 passed.

- [ ] **Step 10: Commit**

```bash
git add core/db/models.py core/voice/pipeline.py tests/test_db.py tests/test_voice_pipeline.py
git commit -m "feat(core): add RouteDecision logging and voice pipeline orchestration"
```

---

### Task 9: Backend endpoints

**Files:**
- Modify: `apps/core/core/app.py`
- Create: `apps/core/tests/test_voice_endpoints.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Consumes: `run_voice_pipeline` (Task 8), `clear_voice_dir` (Task 7), `BASE_DIR` (existing, `app.py`).
- Produces: `POST /voice/invoke` (multipart `audio` file → pipeline → JSON response), `GET /voice/audio/{audio_id}` (serves the generated WAV; validates `audio_id` is a UUID). Task 12/13 (contract + smoke tests) call these over real HTTP.

- [ ] **Step 1: Add the python-multipart dependency**

Append to `apps/core/requirements.txt`:
```
python-multipart>=0.0.12
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `apps/core/tests/test_voice_endpoints.py`:
```python
import io

from fastapi.testclient import TestClient

from core.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("JARVIS_VOICE_DIR", str(tmp_path / "voice"))
    app = create_app()
    return TestClient(app), app


class FakeSTT:
    def transcribe(self, audio_path):
        return "say hi to me"


class FakeTTS:
    def synthesize(self, text, output_path):
        output_path.write_bytes(b"RIFF-fake-wav-bytes")


class FakeRouterLLM:
    def complete(self, prompt, *, system=None):
        return '{"skill_id": "echo", "inputs": {"text": "hi"}}'


def _wire_fakes(app, monkeypatch):
    app.state.stt_provider = FakeSTT()
    app.state.tts_provider = FakeTTS()
    monkeypatch.setattr("core.voice.pipeline.get_llm_provider", lambda settings: FakeRouterLLM())


def test_voice_invoke_returns_full_pipeline_result(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _wire_fakes(app, monkeypatch)

    response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b"fake-audio-bytes"), "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "say hi to me"
    assert body["skill_id"] == "echo"
    assert body["audio_url"].startswith("/voice/audio/")


def test_voice_invoke_returns_400_for_empty_upload(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b""), "audio/webm")},
    )

    assert response.status_code == 400


def test_get_voice_audio_serves_generated_file(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    _wire_fakes(app, monkeypatch)

    invoke_response = client.post(
        "/voice/invoke",
        files={"audio": ("clip.webm", io.BytesIO(b"fake-audio-bytes"), "audio/webm")},
    )
    audio_url = invoke_response.json()["audio_url"]

    audio_response = client.get(audio_url)

    assert audio_response.status_code == 200
    assert audio_response.content == b"RIFF-fake-wav-bytes"


def test_get_voice_audio_rejects_non_uuid_id(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.get("/voice/audio/not-a-uuid")

    assert response.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_voice_endpoints.py -v`
Expected: FAIL — `404 Not Found` (routes don't exist yet).

- [ ] **Step 4: Add the endpoints**

Read the current contents of `apps/core/core/app.py` first. Add these imports alongside the existing ones:
```python
import uuid

from fastapi import UploadFile, File
from fastapi.responses import FileResponse

from core.voice.files import clear_voice_dir
from core.voice.pipeline import run_voice_pipeline
```

Then, inside `create_app()`, immediately after the line `app.state.tts_provider = get_tts_provider(settings)` (added in Task 4), add:
```python
    clear_voice_dir(BASE_DIR / settings.voice_dir)
```
This clears any stale uploads/TTS files left over from a previous run — per the design's Temp File Lifecycle section, `voice_dir` contents have no consumers across a restart.

Then, still inside `create_app()`, add these two routes after the existing `invoke_skill` route (before the `@app.websocket("/ws")` route):
```python
    @app.post("/voice/invoke")
    async def voice_invoke(audio: UploadFile = File(...)):
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio upload")
        extension = Path(audio.filename or "clip.webm").suffix.lstrip(".") or "webm"
        return await run_voice_pipeline(app, audio_bytes, extension)

    @app.get("/voice/audio/{audio_id}")
    def get_voice_audio(audio_id: str):
        try:
            uuid.UUID(audio_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid audio id")
        path = BASE_DIR / settings.voice_dir / "tts" / f"{audio_id}.wav"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio not found")
        return FileResponse(path, media_type="audio/wav")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_voice_endpoints.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

- [ ] **Step 7: Commit**

```bash
git add core/app.py tests/test_voice_endpoints.py requirements.txt
git commit -m "feat(core): add POST /voice/invoke and GET /voice/audio/{id} endpoints"
```

---

### Task 10: Frontend API client — invokeVoice()

**Files:**
- Modify: `apps/desktop/src/api/client.ts`
- Modify: `apps/desktop/src/api/client.test.ts`

**Interfaces:**
- Produces: `VoiceInvokeResponse` interface, `invokeVoice(audio: Blob): Promise<VoiceInvokeResponse>`, `voiceAudioUrl(path: string): string`. Task 11's `VoiceButton` component imports all three.

- [ ] **Step 1: Write the failing tests**

Read the current contents of `apps/desktop/src/api/client.test.ts` first (to match its existing import line). Append these two `describe` blocks:
```typescript
describe("invokeVoice", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts multipart form data and returns the parsed pipeline result", async () => {
    const mockResult = {
      invocation_id: "abc-123",
      transcript: "what is two plus two",
      skill_id: "ask",
      fallback_used: true,
      fallback_reason: "model_chose_ask",
      outputs: { response: "4" },
      response_text: "4",
      audio_url: "/voice/audio/abc-123",
      error: null,
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResult,
    } as Response);

    const blob = new Blob(["fake-audio-bytes"], { type: "audio/webm" });
    const result = await invokeVoice(blob);

    expect(result).toEqual(mockResult);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toBe("http://127.0.0.1:8420/voice/invoke");
    expect(call[1].method).toBe("POST");
    expect((call[1].body as FormData).get("audio")).toBeInstanceOf(Blob);
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "pipeline error" }),
    } as Response);

    const blob = new Blob(["fake-audio-bytes"], { type: "audio/webm" });
    await expect(invokeVoice(blob)).rejects.toThrow("Failed to invoke voice: 500");
  });
});

describe("voiceAudioUrl", () => {
  it("prefixes the path with the backend base URL", () => {
    expect(voiceAudioUrl("/voice/audio/abc-123")).toBe(
      "http://127.0.0.1:8420/voice/audio/abc-123"
    );
  });
});
```

Update the file's import line at the top to include the new functions:
```typescript
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl } from "./client";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/desktop && npm test`
Expected: FAIL — `invokeVoice is not defined` / TypeScript error.

- [ ] **Step 3: Implement invokeVoice and voiceAudioUrl**

Read the current contents of `apps/desktop/src/api/client.ts` first. Append this to the end of the file:
```typescript
export interface VoiceInvokeResponse {
  invocation_id: string;
  transcript: string;
  skill_id: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  outputs: Record<string, unknown> | null;
  response_text: string;
  audio_url: string | null;
  error: string | null;
}

export async function invokeVoice(audio: Blob): Promise<VoiceInvokeResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "clip.webm");
  const response = await fetch(`${BASE_URL}/voice/invoke`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(`Failed to invoke voice: ${response.status} ${JSON.stringify(body)}`);
  }
  return response.json();
}

export function voiceAudioUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/desktop && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/client.ts src/api/client.test.ts
git commit -m "feat(desktop): add invokeVoice API client function"
```
(Run this from `apps/desktop/`.)

---

### Task 11: VoiceButton component + App integration

**Files:**
- Create: `apps/desktop/src/components/VoiceButton.tsx`
- Create: `apps/desktop/src/components/VoiceButton.test.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: `invokeVoice`, `voiceAudioUrl`, `VoiceInvokeResponse` (Task 10).
- Produces: `VoiceButton` component, rendered in `App.tsx` above the skill list.

- [ ] **Step 1: Write the failing VoiceButton tests**

Create `apps/desktop/src/components/VoiceButton.test.tsx`:
```typescript
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VoiceButton } from "./VoiceButton";
import * as client from "../api/client";

afterEach(() => cleanup());

class FakeMediaRecorder {
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: unknown) {}
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(["chunk"]) });
    this.onstop?.();
  }
}

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

beforeEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn().mockResolvedValue({}) },
    configurable: true,
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

describe("VoiceButton", () => {
  it("renders in idle state with a hold-to-talk button", () => {
    render(<VoiceButton />);
    expect(screen.getByTestId("voice-button")).toHaveTextContent("Hold to talk");
  });

  it("records then invokes voice and shows the result on release", async () => {
    vi.spyOn(client, "invokeVoice").mockResolvedValue({
      invocation_id: "abc-123",
      transcript: "what is two plus two",
      skill_id: "ask",
      fallback_used: true,
      fallback_reason: "model_chose_ask",
      outputs: { response: "4" },
      response_text: "4",
      audio_url: null,
      error: null,
    });

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");

    fireEvent.mouseDown(button);
    expect(button).toHaveTextContent("Recording");

    fireEvent.mouseUp(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-result")).toHaveTextContent("what is two plus two");
    });
    expect(screen.getByTestId("voice-result")).toHaveTextContent("fell back to ask");
  });

  it("shows an error message when invokeVoice rejects", async () => {
    vi.spyOn(client, "invokeVoice").mockRejectedValue(new Error("backend down"));

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-error")).toHaveTextContent("backend down");
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/desktop && npm test`
Expected: FAIL — cannot find module `./VoiceButton`.

- [ ] **Step 3: Implement VoiceButton**

Create `apps/desktop/src/components/VoiceButton.tsx`:
```tsx
import { useEffect, useRef, useState } from "react";
import type { VoiceInvokeResponse } from "../api/client";
import { invokeVoice, voiceAudioUrl } from "../api/client";

type VoiceState = "idle" | "recording" | "processing" | "playing" | "error";

const WS_URL = "ws://127.0.0.1:8420/ws";

const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribing…",
  routing: "Routing…",
  invoking_skill: "Running the skill…",
  synthesizing: "Speaking…",
  done: "",
  error: "Something went wrong.",
};

export function VoiceButton() {
  const [state, setState] = useState<VoiceState>("idle");
  const [statusLabel, setStatusLabel] = useState("");
  const [result, setResult] = useState<VoiceInvokeResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const invocationIdRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type !== "voice_status") return;
      if (data.invocation_id !== invocationIdRef.current) return;
      setStatusLabel(STAGE_LABELS[data.stage] ?? "");
    };
    return () => ws.close();
  }, []);

  const startRecording = async () => {
    setErrorMessage(null);
    setResult(null);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      void handleRecordingComplete();
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setState("recording");
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
  };

  const handleRecordingComplete = async () => {
    setState("processing");
    setStatusLabel("Transcribing…");
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    try {
      const response = await invokeVoice(blob);
      invocationIdRef.current = response.invocation_id;
      setResult(response);
      if (response.audio_url && audioRef.current) {
        audioRef.current.src = voiceAudioUrl(response.audio_url);
        setState("playing");
        await audioRef.current.play().catch(() => {});
      } else {
        setState("idle");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4 mb-4">
      <button
        data-testid="voice-button"
        disabled={state === "processing"}
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onMouseLeave={() => {
          if (state === "recording") stopRecording();
        }}
        className="bg-purple-600 text-white rounded px-3 py-1"
      >
        {state === "recording" ? "Recording… release to send" : "Hold to talk"}
      </button>
      {statusLabel && <p data-testid="voice-status">{statusLabel}</p>}
      {result && (
        <div data-testid="voice-result" className="mt-2 text-sm bg-gray-100 p-2 rounded">
          <p>Transcript: {result.transcript}</p>
          <p>
            Skill: {result.skill_id}
            {result.fallback_used && " (fell back to ask)"}
          </p>
          <p>{result.response_text}</p>
        </div>
      )}
      {errorMessage && (
        <p data-testid="voice-error" className="mt-2 text-sm text-red-600">
          {errorMessage}
        </p>
      )}
      <audio ref={audioRef} data-testid="voice-audio" onEnded={() => setState("idle")} />
    </div>
  );
}
```

- [ ] **Step 4: Run VoiceButton tests to verify they pass**

Run: `cd apps/desktop && npm test`
Expected: PASS (3 new tests in `VoiceButton.test.tsx`).

- [ ] **Step 5: Integrate into App.tsx**

Read the current contents of `apps/desktop/src/App.tsx` first. Add the import:
```typescript
import { VoiceButton } from "./components/VoiceButton";
```

Add `<VoiceButton />` immediately after the error paragraph and before the `{skills.map(...)}` line:
```tsx
      <VoiceButton />
```

- [ ] **Step 6: Update App.test.tsx to stub WebSocket**

Read the current contents of `apps/desktop/src/App.test.tsx` first. `VoiceButton` now opens a real `WebSocket` in a `useEffect` on mount, which jsdom does not implement — add a stub so the existing App tests don't fail. Add this class and `beforeEach` stub (in addition to the existing `beforeEach` that calls `vi.restoreAllMocks()` — merge into the same block):
```typescript
class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}
```
Update the existing `beforeEach` in the `describe("App", ...)` block to also stub the global:
```typescript
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
```

- [ ] **Step 7: Run the full frontend suite**

Run: `cd apps/desktop && npm test`
Expected: 15 passed (9 from Milestone 3, plus 3 from Task 10, plus 3 from this task).

- [ ] **Step 8: Commit**

```bash
git add src/components/VoiceButton.tsx src/components/VoiceButton.test.tsx src/App.tsx src/App.test.tsx
git commit -m "feat(desktop): add push-to-talk VoiceButton and wire into App"
```
(Run this from `apps/desktop/`.)

---

### Task 12: Live contract tests

**Files:**
- Create: `apps/core/tests/test_faster_whisper_contract.py`
- Create: `apps/core/tests/test_piper_contract.py`

**Interfaces:** None new — these exercise the real `FasterWhisperProvider` (Task 2) and `PiperProvider` (Task 3) against real backends when available, mirroring `test_llm_provider_contract.py`'s skip pattern from Milestone 3.

- [ ] **Step 1: Generate a real speech fixture**

```bash
say -v Alice -o /tmp/sample_speech.aiff "This is a test"
mkdir -p apps/core/tests/fixtures
afconvert -f WAVE -d LEI16 /tmp/sample_speech.aiff apps/core/tests/fixtures/sample_speech.wav
```
Expected: `apps/core/tests/fixtures/sample_speech.wav` exists (macOS's built-in `say` + `afconvert` produce a real, deterministic spoken-audio WAV — no internet or microphone needed).

- [ ] **Step 2: Write the contract tests**

Create `apps/core/tests/test_faster_whisper_contract.py`:
```python
from pathlib import Path

import pytest

from core.config import Settings
from core.providers.stt.faster_whisper_provider import FasterWhisperProvider

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_speech.wav"


def _faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample_speech.wav fixture not present")
@pytest.mark.skipif(not _faster_whisper_available(), reason="faster-whisper not installed")
def test_faster_whisper_transcribes_real_audio():
    provider = FasterWhisperProvider(Settings(anthropic_api_key=None))

    result = provider.transcribe(FIXTURE)

    assert isinstance(result, str)
    assert len(result) > 0
```

Create `apps/core/tests/test_piper_contract.py`:
```python
import shutil

import pytest

from core.config import Settings
from core.providers.tts.piper_provider import PiperProvider


@pytest.mark.skipif(shutil.which("piper") is None, reason="piper CLI not installed")
def test_piper_produces_nonempty_wav(tmp_path):
    provider = PiperProvider(Settings(anthropic_api_key=None))
    output_path = tmp_path / "out.wav"

    provider.synthesize("This is a test.", output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
```

- [ ] **Step 3: Run the contract tests to confirm skip behavior**

Run: `.venv/bin/pytest tests/test_faster_whisper_contract.py tests/test_piper_contract.py -v`
Expected: both SKIPPED (unless this environment already has `faster-whisper` installed and/or `piper` on `PATH` — if so, that test runs for real instead of skipping, which is also correct).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 81 collected (79 from Task 9, plus 2 new — passed count may be 79-81 depending on whether either contract test skips or runs for real in this environment).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sample_speech.wav tests/test_faster_whisper_contract.py tests/test_piper_contract.py
git commit -m "test(core): add live contract tests for FasterWhisperProvider and PiperProvider"
```

---

### Task 13: End-to-End Manual Smoke Test

**Files:** None (verification only).

**Interfaces:** None — this task exercises the full stack built across Tasks 1-12, including installing real STT/TTS backends the automated suite cannot assume are present.

- [ ] **Step 1: Install system dependencies**

```bash
cd apps/core
.venv/bin/pip install faster-whisper piper-tts
which ffmpeg || brew install ffmpeg
```
Expected: both Python packages install without error; `ffmpeg` available (faster-whisper needs it to decode the browser's webm/opus recordings).

- [ ] **Step 2: Download the Piper voice model**

```bash
mkdir -p apps/core/voices
curl -L -o apps/core/voices/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o apps/core/voices/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```
Expected: two files downloaded (a few dozen MB total). If either URL has moved, search "piper-voices en_US-lessac-medium huggingface" for the current location.

- [ ] **Step 3: Confirm the live contract tests now run for real**

```bash
JARVIS_PIPER_VOICE="$(pwd)/voices/en_US-lessac-medium.onnx" .venv/bin/pytest tests/test_faster_whisper_contract.py tests/test_piper_contract.py -v
```
Expected: both PASSED (faster-whisper downloads the `small` model to its local cache on first run — may take a minute).

- [ ] **Step 4: Start the backend**

```bash
JARVIS_PIPER_VOICE="$(pwd)/voices/en_US-lessac-medium.onnx" nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m4-smoke.log 2>&1 &
BACKEND_PID=$!
sleep 3
curl -s http://127.0.0.1:8420/skills
```
Expected: JSON array including both the `echo` and `ask` skill manifests, confirming clean startup with the new STT/TTS providers wired in.

- [ ] **Step 5: Exercise the full pipeline via curl**

```bash
say -v Alice -o /tmp/smoke_test.aiff "What is two plus two"
afconvert -f WAVE -d LEI16 /tmp/smoke_test.aiff /tmp/smoke_test.wav
curl -s -X POST http://127.0.0.1:8420/voice/invoke -F "audio=@/tmp/smoke_test.wav" | python3 -m json.tool
```
Expected: a JSON response with a non-empty `transcript` roughly matching "what is two plus two", a `response_text` containing an answer, and a non-null `audio_url`.

- [ ] **Step 6: Play the generated audio**

```bash
AUDIO_URL=$(curl -s -X POST http://127.0.0.1:8420/voice/invoke -F "audio=@/tmp/smoke_test.wav" | python3 -c "import sys, json; print(json.load(sys.stdin)['audio_url'])")
curl -s "http://127.0.0.1:8420$AUDIO_URL" -o /tmp/smoke_response.wav
afplay /tmp/smoke_response.wav
```
Expected: the downloaded WAV plays audibly, speaking the answer.

- [ ] **Step 7: Test the fallback path**

```bash
say -v Alice -o /tmp/smoke_test2.aiff "Repeat after me the quick brown fox"
afconvert -f WAVE -d LEI16 /tmp/smoke_test2.aiff /tmp/smoke_test2.wav
curl -s -X POST http://127.0.0.1:8420/voice/invoke -F "audio=@/tmp/smoke_test2.wav" | python3 -m json.tool
```
Expected: the router either correctly picks `echo` with an extracted `text` input, or falls back to `ask` — either is a valid pass, since it confirms real routing logic ran against a real transcript. Note which one happened in your report.

- [ ] **Step 8: Confirm route decisions were logged**

```bash
.venv/bin/python3 -c "
from core.config import get_settings
from core.db.database import make_engine, make_session_factory
from core.db.models import RouteDecision
engine = make_engine(get_settings().database_url)
with make_session_factory(engine)() as session:
    for row in session.query(RouteDecision).all():
        print(row.skill_id, row.fallback_used, row.fallback_reason)
"
```
Expected: one row printed per `/voice/invoke` call made in Steps 5-7 — confirms the design review's Router Logging requirement is actually being written.

- [ ] **Step 9: Test the desktop UI (if a display is attached)**

```bash
cd ../desktop
nohup npm run tauri dev > /tmp/jarvis-desktop-m4-smoke.log 2>&1 &
DESKTOP_PID=$!
sleep 20
```
If a display is attached: hold the "Hold to talk" button, say "what is two plus two," release, and confirm the status line updates live, the result panel shows the transcript/skill/answer, and the answer plays audibly. If no display is attached, skip this step and rely on Steps 5-8 plus the automated suites as evidence; note this explicitly in your report.

- [ ] **Step 10: Stop all processes**

```bash
kill $BACKEND_PID 2>/dev/null
kill $DESKTOP_PID 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
pkill -f "vite" 2>/dev/null
```

- [ ] **Step 11: Run both full test suites one final time**

```bash
cd apps/core && .venv/bin/pytest -v
cd ../desktop && npm test
```
Expected: all backend tests pass (around 81, per Task 12's count), all frontend tests pass (15, per Task 11's count). No failures.

No commit for this task — it's verification only.
