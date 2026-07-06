# Jarvis OS Milestone 5: Claude Code Integration Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `claude_code_task` skill that headlessly invokes the Claude Code CLI against the Jarvis OS repo, streaming live progress over the existing WebSocket bus while the skill itself returns a `task_id` immediately.

**Architecture:** A new `TaskManager` core service owns the full lifecycle of a background subprocess (spawn via `asyncio.create_subprocess_exec`, read its `stream-json` NDJSON output incrementally, enforce a timeout with process-group kill, persist state to a new `ClaudeCodeTask` DB table, publish `claude_code_task` WebSocket events). The skill's `run()` stays a fast, synchronous function — it validates inputs and asks `TaskManager` to start the task, returning the task id immediately; it does not change the existing skill contract at all.

**Tech Stack:** Python 3.14, FastAPI (existing), `asyncio` subprocess APIs (stdlib, no new dependency), SQLAlchemy 2.0 (existing). Backend-only milestone — no frontend UI task (per the design's own scope: the manual smoke test and testing strategy validate backend behavior; a `TaskPanel.tsx` UI is deferred to whenever this milestone's backend has proven itself, consistent with keeping scope tight).

## Global Constraints

- Run all commands from `apps/core/` using `.venv/bin/python3` / `.venv/bin/pytest`.
- New dependencies (if any) go in `apps/core/requirements.txt` with a flexible `>=` minimum-version pin. This milestone needs none — everything is stdlib (`asyncio`, `subprocess`, `os`, `signal`, `shutil`).
- Every task ends with a full `.venv/bin/pytest -v` run.
- `claude_code_task` skill: `voice_invokable: false`, `background: true` in its manifest — never voice-routable.
- The task's working directory is fixed to the Jarvis OS repo root (computed from `Path(__file__).resolve()` ancestors, matching the existing `BASE_DIR` convention in `core/app.py`) or a validated subpath within it — never a caller-supplied absolute path.
- Subprocess invocation uses `--output-format stream-json` (not `json`) with `asyncio.create_subprocess_exec` (argv-only, no shell) — the CLI's own permission system plus `--allowedTools` (excluding unrestricted `Bash`) are the containment layers, not `cwd` alone.
- `start_new_session=True` on subprocess creation; kill sequence on timeout/failure is `os.killpg(pgid, SIGTERM)` → wait up to 5s → `os.killpg(pgid, SIGKILL)` → `await process.wait()`.
- Every task reaches exactly one terminal state (`completed`, `failed`, `timed_out`, or `interrupted` at next startup for restart orphans), guaranteed structurally by a `finally`-equivalent code path — never left stuck in `running` while the process is gone.
- No auto-commit of the agent's file changes, ever. No manual-cancellation endpoint this milestone. No task queueing/concurrency limits this milestone.
- WebSocket event shape: `{"type": "claude_code_task", "task_id": "<uuid>", "stage": "<stage>", "detail": {...}}` with stages `started`, `tool_use`, `assistant_text`, `completed`, `failed`, `timed_out`.

---

### Task 1: Config extension + SkillManifest `background` field

**Files:**
- Modify: `apps/core/core/config.py`
- Modify: `apps/core/tests/test_config.py`
- Modify: `apps/core/core/skills/manifest.py`
- Modify: `apps/core/tests/test_manifest.py`

**Interfaces:**
- Produces: `Settings.claude_code_binary: str`, `Settings.claude_code_subpath: str`, `Settings.claude_code_timeout_seconds: int`, `Settings.claude_code_allowed_tools: str`, `Settings.claude_code_max_turns: int` — every later task reads these off a `Settings` instance.
- Produces: `SkillManifest.background: bool = False` — used by the skill's manifest and, informationally, by any future UI.

- [ ] **Step 1: Write the failing config test**

Append to `apps/core/tests/test_config.py`:
```python
def test_claude_code_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.claude_code_binary == "claude"
    assert settings.claude_code_subpath == ""
    assert settings.claude_code_timeout_seconds == 600
    assert settings.claude_code_allowed_tools == (
        "Read,Glob,Grep,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
    )
    assert settings.claude_code_max_turns == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py::test_claude_code_settings_defaults -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'claude_code_binary'`.

- [ ] **Step 3: Extend Settings**

Read the current contents of `apps/core/core/config.py` first, then add these fields to the `Settings` class (after the existing `voice_dir` field, before `def get_settings()`):
```python
    claude_code_binary: str = "claude"
    claude_code_subpath: str = ""
    claude_code_timeout_seconds: int = 600
    claude_code_allowed_tools: str = (
        "Read,Glob,Grep,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
    )
    claude_code_max_turns: int = 50
```

- [ ] **Step 4: Run config test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 5: Write the failing manifest tests**

Append to `apps/core/tests/test_manifest.py`:
```python
def test_manifest_background_defaults_to_false(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        "id: test_skill\nname: Test\ndescription: A test skill.\n"
    )
    manifest = load_manifest(manifest_path)
    assert manifest.background is False


def test_manifest_background_can_be_set_true(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        "id: test_skill\nname: Test\ndescription: A test skill.\nbackground: true\n"
    )
    manifest = load_manifest(manifest_path)
    assert manifest.background is True
```

If `tests/test_manifest.py` doesn't already import `load_manifest`, check the file's existing imports first and match them — it should already import from `core.skills.manifest`.

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_manifest.py -v -k background`
Expected: FAIL — `TypeError` or `AttributeError` (no `background` field yet).

- [ ] **Step 7: Add the field**

Read the current contents of `apps/core/core/skills/manifest.py` first. Add `background: bool = False` to the `SkillManifest` class, immediately after `voice_invokable: bool = False`:
```python
    voice_invokable: bool = False
    background: bool = False
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 86 passed, 1 skipped (83 passed/1 skipped from Milestone 4, plus 3 new: 1 config + 2 manifest).

- [ ] **Step 10: Commit**

```bash
git add core/config.py core/skills/manifest.py tests/test_config.py tests/test_manifest.py
git commit -m "feat(core): add Claude Code settings and manifest background field"
```

---

### Task 2: ClaudeCodeTask DB model

**Files:**
- Modify: `apps/core/core/db/models.py`
- Modify: `apps/core/tests/test_db.py`

**Interfaces:**
- Produces: `ClaudeCodeTask` SQLAlchemy model with columns `task_id` (str, PK), `prompt`, `working_dir`, `status`, `result_text`, `error`, `num_turns`, `duration_ms`, `cost_usd`, `created_at`, `finished_at`. `TaskManager` (Task 4) and the endpoints (Task 8) both read/write this table.

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_db.py`:
```python
def test_claude_code_task_can_be_created_and_queried():
    from core.db.models import ClaudeCodeTask

    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        session.add(
            ClaudeCodeTask(
                task_id="abc-123",
                prompt="add a docstring",
                working_dir="/tmp/jarvis-os",
                status="running",
            )
        )
        session.commit()

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, "abc-123")
        assert row.prompt == "add a docstring"
        assert row.working_dir == "/tmp/jarvis-os"
        assert row.status == "running"
        assert row.result_text is None
        assert row.error is None
        assert row.created_at is not None
        assert row.finished_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py::test_claude_code_task_can_be_created_and_queried -v`
Expected: FAIL — `ImportError: cannot import name 'ClaudeCodeTask'`.

- [ ] **Step 3: Add the model**

Read the current contents of `apps/core/core/db/models.py` first. Add `Float` to the existing `from sqlalchemy import ...` line (alongside `Boolean, DateTime, Integer, JSON, String`). Then add this class after `RouteDecision`:
```python
class ClaudeCodeTask(Base):
    __tablename__ = "claude_code_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    working_dir: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    result_text: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    num_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: PASS (all tests in the file, including pre-existing ones).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 87 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/db/models.py tests/test_db.py
git commit -m "feat(core): add ClaudeCodeTask DB model"
```

---

### Task 3: NDJSON stream parsing

**Files:**
- Create: `apps/core/core/tasks/__init__.py` (empty)
- Create: `apps/core/core/tasks/stream.py`
- Create: `apps/core/tests/test_task_stream.py`

**Interfaces:**
- Produces: `TaskEvent` dataclass (`stage: str`, `detail: dict`), `parse_stream_line(line: str) -> TaskEvent | None`. Pure function — no I/O, no side effects. `TaskManager` (Task 4) is the only consumer.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_task_stream.py`:
```python
import json

from core.tasks.stream import TaskEvent, parse_stream_line


def test_parses_tool_use_event_with_file_path():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "foo.py"}}]},
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Edit", "summary": "foo.py"})


def test_parses_tool_use_event_with_command():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "git status"}}]},
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Bash", "summary": "git status"})


def test_parses_assistant_text_event_and_truncates_to_500_chars():
    long_text = "x" * 600
    line = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": long_text}]}})

    event = parse_stream_line(line)

    assert event.stage == "assistant_text"
    assert event.detail["text"] == "x" * 500


def test_tool_use_takes_priority_over_text_in_the_same_message():
    line = json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "About to edit a file."},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "bar.py"}},
            ]
        },
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(stage="tool_use", detail={"tool": "Edit", "summary": "bar.py"})


def test_parses_result_event():
    line = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": "Done.",
        "num_turns": 3,
        "duration_ms": 1200,
        "total_cost_usd": 0.05,
    })

    event = parse_stream_line(line)

    assert event == TaskEvent(
        stage="result",
        detail={
            "subtype": "success",
            "result": "Done.",
            "num_turns": 3,
            "duration_ms": 1200,
            "cost_usd": 0.05,
        },
    )


def test_skips_system_event():
    assert parse_stream_line(json.dumps({"type": "system", "subtype": "init"})) is None


def test_skips_user_event():
    assert parse_stream_line(json.dumps({"type": "user", "message": {}})) is None


def test_returns_none_for_malformed_json():
    assert parse_stream_line("not json at all") is None


def test_returns_none_for_blank_line():
    assert parse_stream_line("   \n") is None


def test_returns_none_for_non_dict_json():
    assert parse_stream_line("[1, 2, 3]") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_task_stream.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tasks'`.

- [ ] **Step 3: Implement the parser**

Create `apps/core/core/tasks/__init__.py` (empty file).

Create `apps/core/core/tasks/stream.py`:
```python
import json
from dataclasses import dataclass


@dataclass
class TaskEvent:
    stage: str
    detail: dict


def _tool_use_summary(block: dict) -> str:
    tool_input = block.get("input", {})
    if "file_path" in tool_input:
        return str(tool_input["file_path"])
    if "command" in tool_input:
        return str(tool_input["command"])
    if tool_input:
        return str(next(iter(tool_input.values())))
    return ""


def parse_stream_line(line: str) -> TaskEvent | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    event_type = parsed.get("type")

    if event_type == "assistant":
        content = parsed.get("message", {}).get("content", [])
        for block in content:
            if block.get("type") == "tool_use":
                return TaskEvent(
                    stage="tool_use",
                    detail={"tool": block.get("name", "unknown"), "summary": _tool_use_summary(block)},
                )
        for block in content:
            if block.get("type") == "text":
                text = block.get("text", "")
                return TaskEvent(stage="assistant_text", detail={"text": text[:500]})
        return None

    if event_type == "result":
        return TaskEvent(
            stage="result",
            detail={
                "subtype": parsed.get("subtype"),
                "result": parsed.get("result"),
                "num_turns": parsed.get("num_turns"),
                "duration_ms": parsed.get("duration_ms"),
                "cost_usd": parsed.get("total_cost_usd"),
            },
        )

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_task_stream.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 97 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/tasks/__init__.py core/tasks/stream.py tests/test_task_stream.py
git commit -m "feat(core): add NDJSON stream-json line parser"
```

---

### Task 4: Stub CLI fixture + TaskManager core (happy path + failure path)

**Files:**
- Create: `apps/core/tests/fixtures/stub_claude_cli.py`
- Create: `apps/core/core/tasks/manager.py`
- Create: `apps/core/tests/test_task_manager.py`

**Interfaces:**
- Consumes: `parse_stream_line`/`TaskEvent` (Task 3), `ClaudeCodeTask` (Task 2), `EventBus` (existing, M1), `Settings` (Task 1).
- Produces: `TaskManager(settings, session_factory, event_bus)`, with methods `bind_loop(loop: asyncio.AbstractEventLoop) -> None` and `start(prompt: str, working_dir: Path) -> str` (returns a `task_id`, schedules the background run via `asyncio.run_coroutine_threadsafe`). Task 5 extends this same class with timeout handling. Task 6 wires `bind_loop` into app startup. The skill (Task 7) calls `start()`.

This task does NOT include the timeout wrapper — that's Task 5. This task's `_run` reads the subprocess to completion (or failure) with no time limit, to keep this task's diff reviewable independently.

- [ ] **Step 1: Create the stub CLI fixture**

Create `apps/core/tests/fixtures/stub_claude_cli.py`:
```python
#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests. Behavior controlled via env vars:

STUB_CLI_MODE=success|failure (default: success)
STUB_CLI_PID_FILE=<path> (optional) — if set, spawns a child process and
    writes this process's PID and the child's PID to the file, one per line,
    for tests that verify no orphaned processes survive a kill.
"""
import json
import os
import subprocess
import sys


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def main() -> None:
    mode = os.environ.get("STUB_CLI_MODE", "success")
    pid_file = os.environ.get("STUB_CLI_PID_FILE")

    if pid_file:
        child = subprocess.Popen(["sleep", "60"])
        with open(pid_file, "w") as f:
            f.write(f"{os.getpid()}\n{child.pid}\n")

    emit({"type": "system", "subtype": "init"})
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "foo.py"}}]}})
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on it."}]}})
    print("not valid json at all", flush=True)

    if os.environ.get("STUB_CLI_SLOW") == "1":
        import time
        time.sleep(120)

    if mode == "failure":
        emit({
            "type": "result", "subtype": "error_max_turns", "result": "failed",
            "num_turns": 1, "duration_ms": 10, "total_cost_usd": 0.01,
        })
        sys.exit(1)

    emit({
        "type": "result", "subtype": "success", "result": "Done.",
        "num_turns": 2, "duration_ms": 500, "total_cost_usd": 0.02,
    })
    sys.exit(0)


if __name__ == "__main__":
    main()
```

Make it executable:
```bash
chmod +x tests/fixtures/stub_claude_cli.py
```

- [ ] **Step 2: Write the failing tests**

Create `apps/core/tests/test_task_manager.py`:
```python
import asyncio
from pathlib import Path

from core.config import Settings
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import ClaudeCodeTask
from core.events.bus import EventBus
from core.tasks.manager import TaskManager

STUB_CLI = str(Path(__file__).resolve().parent / "fixtures" / "stub_claude_cli.py")


def _make_manager(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    session_factory = make_session_factory(engine)
    settings = Settings(anthropic_api_key=None, claude_code_binary=STUB_CLI, claude_code_timeout_seconds=30)
    event_bus = EventBus()
    manager = TaskManager(settings, session_factory, event_bus)
    return manager, session_factory, event_bus


async def _run_and_collect_events(manager, event_bus, working_dir, prompt="do something"):
    manager.bind_loop(asyncio.get_running_loop())
    queue = event_bus.subscribe()
    task_id = manager.start(prompt, working_dir)
    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=10.0)
        events.append(event)
        if event["stage"] in ("completed", "failed", "timed_out"):
            break
    return task_id, events


def test_happy_path_publishes_expected_events_and_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_CLI_MODE", "success")
    manager, session_factory, event_bus = _make_manager(tmp_path)

    task_id, events = asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    stages = [e["stage"] for e in events]
    assert stages == ["started", "tool_use", "assistant_text", "completed"]
    assert events[0]["task_id"] == task_id
    assert events[-1]["detail"]["result_excerpt"] == "Done."
    assert events[-1]["detail"]["cost_usd"] == 0.02

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status == "completed"
        assert row.result_text == "Done."
        assert row.num_turns == 2
        assert row.finished_at is not None


def test_nonzero_exit_marks_task_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_CLI_MODE", "failure")
    manager, session_factory, event_bus = _make_manager(tmp_path)

    task_id, events = asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    assert events[-1]["stage"] == "failed"

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status == "failed"
        assert row.error is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_task_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tasks.manager'`.

- [ ] **Step 4: Implement TaskManager (no timeout yet)**

Create `apps/core/core/tasks/manager.py`:
```python
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.config import Settings
from core.db.models import ClaudeCodeTask
from core.events.bus import EventBus
from core.tasks.stream import parse_stream_line


class TaskManager:
    def __init__(self, settings: Settings, session_factory, event_bus: EventBus) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self, prompt: str, working_dir: Path) -> str:
        task_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                ClaudeCodeTask(task_id=task_id, prompt=prompt, working_dir=str(working_dir), status="running")
            )
            session.commit()
        if self._loop is None:
            raise RuntimeError("TaskManager.bind_loop() must be called before start()")
        asyncio.run_coroutine_threadsafe(self._run(task_id, prompt, working_dir), self._loop)
        return task_id

    async def _publish(self, task_id: str, stage: str, detail: dict) -> None:
        await self._event_bus.publish({"type": "claude_code_task", "task_id": task_id, "stage": stage, "detail": detail})

    def _write_terminal_state(self, task_id: str, status: str, **fields) -> None:
        with self._session_factory() as session:
            row = session.get(ClaudeCodeTask, task_id)
            row.status = status
            for key, value in fields.items():
                setattr(row, key, value)
            row.finished_at = datetime.now(timezone.utc)
            session.commit()

    async def _run(self, task_id: str, prompt: str, working_dir: Path) -> None:
        await self._publish(task_id, "started", {"prompt_excerpt": prompt[:120], "working_dir": str(working_dir)})

        process = await asyncio.create_subprocess_exec(
            self._settings.claude_code_binary,
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", self._settings.claude_code_allowed_tools,
            "--max-turns", str(self._settings.claude_code_max_turns),
            cwd=str(working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        result_detail: dict = {}
        stderr_chunks: list[bytes] = []

        async def read_stdout() -> None:
            assert process.stdout is not None
            while True:
                raw_line = await process.stdout.readline()
                if not raw_line:
                    break
                event = parse_stream_line(raw_line.decode("utf-8", errors="replace"))
                if event is None:
                    continue
                if event.stage == "result":
                    result_detail.update(event.detail)
                else:
                    await self._publish(task_id, event.stage, event.detail)

        async def read_stderr() -> None:
            assert process.stderr is not None
            while True:
                chunk = await process.stderr.read(4096)
                if not chunk:
                    break
                stderr_chunks.append(chunk)

        await asyncio.gather(read_stdout(), read_stderr(), process.wait())

        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        if process.returncode == 0 and result_detail.get("subtype") == "success":
            await self._publish(task_id, "completed", {
                "result_excerpt": (result_detail.get("result") or "")[:500],
                "duration_ms": result_detail.get("duration_ms"),
                "cost_usd": result_detail.get("cost_usd"),
            })
            self._write_terminal_state(
                task_id, "completed",
                result_text=result_detail.get("result"),
                num_turns=result_detail.get("num_turns"),
                duration_ms=result_detail.get("duration_ms"),
                cost_usd=result_detail.get("cost_usd"),
            )
        else:
            error_message = stderr_text[-1000:] if stderr_text else f"exited with code {process.returncode}"
            await self._publish(task_id, "failed", {"error": error_message})
            self._write_terminal_state(task_id, "failed", error=error_message)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_task_manager.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 99 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/stub_claude_cli.py core/tasks/manager.py tests/test_task_manager.py
git commit -m "feat(core): add TaskManager (happy path + failure path)"
```

---

### Task 5: TaskManager timeout + process-group kill

**Files:**
- Modify: `apps/core/core/tasks/manager.py`
- Modify: `apps/core/tests/test_task_manager.py`

**Interfaces:**
- Consumes: `TaskManager` from Task 4 (this task modifies `_run` in place).
- Produces: the same `TaskManager.start()` interface, now additionally guaranteeing a `timed_out` terminal state and killing the full process tree when `claude_code_timeout_seconds` is exceeded.

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_task_manager.py` (add `import os` and `import time` and `import pytest` to the top of the file alongside the existing imports):
```python
def test_timeout_kills_process_group_and_marks_timed_out(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_CLI_SLOW", "1")
    pid_file = tmp_path / "pids.txt"
    monkeypatch.setenv("STUB_CLI_PID_FILE", str(pid_file))

    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    session_factory = make_session_factory(engine)
    settings = Settings(anthropic_api_key=None, claude_code_binary=STUB_CLI, claude_code_timeout_seconds=1)
    event_bus = EventBus()
    manager = TaskManager(settings, session_factory, event_bus)

    task_id, events = asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    assert events[-1]["stage"] == "timed_out"

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status == "timed_out"

    time.sleep(0.5)
    pids = [int(p) for p in pid_file.read_text().split()]
    assert len(pids) == 2
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
```

Note this test builds its own `Settings`/`session_factory`/`event_bus` directly (rather than using `_make_manager`, whose default `claude_code_timeout_seconds=30` wouldn't exercise the timeout) so it can set `claude_code_timeout_seconds=1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_task_manager.py::test_timeout_kills_process_group_and_marks_timed_out -v`
Expected: FAIL — the test times out waiting for a `timed_out`/`completed`/`failed` event that never arrives (the stub sleeps 120s and there is no timeout enforcement yet), or hits the `asyncio.wait_for(queue.get(), timeout=10.0)` failure first with a `TimeoutError`.

- [ ] **Step 3: Add timeout enforcement and process-group kill**

Read the current contents of `apps/core/core/tasks/manager.py` first. Add these imports at the top:
```python
import os
import signal
```

Add this new method to `TaskManager`, after `_write_terminal_state`:
```python
    async def _kill_process_group(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        os.killpg(pgid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            os.killpg(pgid, signal.SIGKILL)
            await process.wait()
```

Replace this line in `_run`:
```python
        await asyncio.gather(read_stdout(), read_stderr(), process.wait())
```
with:
```python
        try:
            await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr(), process.wait()),
                timeout=self._settings.claude_code_timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._kill_process_group(process)
            await self._publish(
                task_id, "timed_out", {"timeout_seconds": self._settings.claude_code_timeout_seconds}
            )
            self._write_terminal_state(
                task_id, "timed_out", error=f"timed out after {self._settings.claude_code_timeout_seconds}s"
            )
            return
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `.venv/bin/pytest tests/test_task_manager.py::test_timeout_kills_process_group_and_marks_timed_out -v`
Expected: PASS.

- [ ] **Step 5: Run the full test_task_manager.py file to confirm no regression**

Run: `.venv/bin/pytest tests/test_task_manager.py -v`
Expected: PASS (3 tests — the 2 from Task 4 plus this one).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 100 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add core/tasks/manager.py tests/test_task_manager.py
git commit -m "feat(core): add timeout enforcement and process-group kill to TaskManager"
```

---

### Task 6: TaskManager accessor + app startup wiring

**Files:**
- Create: `apps/core/core/tasks/registry.py`
- Create: `apps/core/tests/test_task_registry.py`
- Modify: `apps/core/core/app.py`
- Create: `apps/core/tests/test_app_startup_tasks.py`

**Interfaces:**
- Produces: `set_task_manager(manager: TaskManager) -> None`, `get_task_manager() -> TaskManager` (raises `RuntimeError` if never set). The skill (Task 7) calls `get_task_manager()`.
- Modifies `create_app()`: constructs a `TaskManager`, registers it via `set_task_manager`, stores it on `app.state.task_manager`, and adds a FastAPI startup event that binds the manager to the running loop and marks any stale `running` `ClaudeCodeTask` rows as `interrupted` (restart-orphan handling).

- [ ] **Step 1: Write the failing registry tests**

Create `apps/core/tests/test_task_registry.py`:
```python
import pytest

from core.tasks.registry import get_task_manager, set_task_manager


def test_raises_before_a_manager_is_set():
    import core.tasks.registry as registry_module
    registry_module._task_manager = None

    with pytest.raises(RuntimeError):
        get_task_manager()


def test_returns_the_manager_after_set():
    sentinel = object()
    set_task_manager(sentinel)

    assert get_task_manager() is sentinel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_task_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tasks.registry'`.

- [ ] **Step 3: Implement the accessor**

Create `apps/core/core/tasks/registry.py`:
```python
_task_manager = None


def set_task_manager(manager) -> None:
    global _task_manager
    _task_manager = manager


def get_task_manager():
    if _task_manager is None:
        raise RuntimeError("TaskManager has not been initialized")
    return _task_manager
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_task_registry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing startup-wiring test**

Create `apps/core/tests/test_app_startup_tasks.py`:
```python
from fastapi.testclient import TestClient

from core.app import create_app
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import ClaudeCodeTask


def test_startup_marks_stale_running_tasks_as_interrupted(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("JARVIS_DATABASE_URL", db_url)

    engine = make_engine(db_url)
    init_db(engine)
    seed_session_factory = make_session_factory(engine)
    with seed_session_factory() as session:
        session.add(
            ClaudeCodeTask(task_id="stale-1", prompt="x", working_dir="/tmp", status="running")
        )
        session.commit()

    app = create_app()
    with TestClient(app):
        with app.state.session_factory() as session:
            row = session.get(ClaudeCodeTask, "stale-1")
            assert row.status == "interrupted"


def test_app_state_has_task_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    assert app.state.task_manager is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_startup_tasks.py -v`
Expected: FAIL — `AttributeError: 'State' object has no attribute 'task_manager'`.

- [ ] **Step 7: Wire TaskManager into create_app()**

Read the current contents of `apps/core/core/app.py` first. Add these imports alongside the existing `core.*` imports:
```python
from core.db.models import ClaudeCodeTask
from core.tasks.manager import TaskManager
from core.tasks.registry import set_task_manager
```

Then, inside `create_app()`, immediately after the line `clear_voice_dir(BASE_DIR / settings.voice_dir)`, add:
```python
    task_manager = TaskManager(settings, app.state.session_factory, app.state.event_bus)
    set_task_manager(task_manager)
    app.state.task_manager = task_manager

    @app.on_event("startup")
    async def _bind_task_manager_and_mark_orphans():
        task_manager.bind_loop(asyncio.get_running_loop())
        with app.state.session_factory() as session:
            orphaned = session.query(ClaudeCodeTask).filter_by(status="running").all()
            for row in orphaned:
                row.status = "interrupted"
            session.commit()
```

`asyncio` is already imported at the top of `app.py` (used by `uuid`/other existing code) — check the current imports first; if `asyncio` is not already imported, add `import asyncio` alongside the existing `import uuid` line.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app_startup_tasks.py -v`
Expected: PASS (2 tests).

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 104 passed, 1 skipped (100 from Task 5, plus 2 registry + 2 startup).

- [ ] **Step 10: Commit**

```bash
git add core/tasks/registry.py core/app.py tests/test_task_registry.py tests/test_app_startup_tasks.py
git commit -m "feat(core): wire TaskManager into app startup with orphan-task recovery"
```

---

### Task 7: The `claude_code_task` skill

**Files:**
- Create: `apps/core/skills/claude_code_task/manifest.yaml`
- Create: `apps/core/skills/claude_code_task/skill.py`
- Create: `apps/core/tests/test_claude_code_task_skill.py`

**Interfaces:**
- Consumes: `get_settings()` (`core.config`), `get_task_manager()` (Task 6).
- Produces: skill id `"claude_code_task"`, loadable via `SkillRegistry`, with `run({"prompt": str, "subpath": str (optional)}) -> {"task_id": str | None, "status": str, "error": str | None}`.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_claude_code_task_skill.py`:
```python
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def test_manifest_is_not_voice_invokable_and_is_background():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("claude_code_task")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False
    assert loaded.manifest.background is True


def test_run_returns_failed_status_when_cli_missing(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type(
        "FakeSettings", (), {"claude_code_binary": "definitely-not-a-real-binary-xyz", "claude_code_subpath": ""}
    )()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    result = loaded.run({"prompt": "do something"})

    assert result["task_id"] is None
    assert result["status"] == "failed"
    assert "claude_cli_not_found" in result["error"]


def test_run_returns_failed_status_for_subpath_escaping_repo(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type("FakeSettings", (), {"claude_code_binary": "python3", "claude_code_subpath": ""})()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    result = loaded.run({"prompt": "do something", "subpath": "../../etc"})

    assert result["task_id"] is None
    assert result["status"] == "failed"
    assert "invalid_subpath" in result["error"]


def test_run_starts_a_task_and_returns_running(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type("FakeSettings", (), {"claude_code_binary": "python3", "claude_code_subpath": ""})()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    class FakeTaskManager:
        def start(self, prompt, working_dir):
            assert prompt == "do something"
            return "fake-task-id"

    monkeypatch.setitem(loaded.run.__globals__, "get_task_manager", lambda: FakeTaskManager())

    result = loaded.run({"prompt": "do something"})

    assert result == {"task_id": "fake-task-id", "status": "running", "error": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_claude_code_task_skill.py -v`
Expected: FAIL — `assert loaded is not None` fails (skill doesn't exist yet).

- [ ] **Step 3: Create the manifest**

Create `apps/core/skills/claude_code_task/manifest.yaml`:
```yaml
id: claude_code_task
name: Claude Code Task
description: Run a coding/agentic task headlessly against the Jarvis OS repo via the Claude Code CLI. Returns a task_id immediately; progress streams over the event bus.
voice_invokable: false
background: true
input_schema:
  type: object
  properties:
    prompt:
      type: string
      minLength: 1
      description: The task for Claude Code to perform.
    subpath:
      type: string
      description: Optional path relative to the repo root to use as the working directory.
  required:
    - prompt
  additionalProperties: false
output_schema:
  type: object
  properties:
    task_id:
      type:
        - string
        - "null"
    status:
      type: string
    error:
      type:
        - string
        - "null"
```

- [ ] **Step 4: Create the skill implementation**

Create `apps/core/skills/claude_code_task/skill.py`:
```python
import shutil
from pathlib import Path

from core.config import get_settings
from core.tasks.registry import get_task_manager

REPO_ROOT = Path(__file__).resolve().parents[4]


def run(inputs: dict) -> dict:
    settings = get_settings()

    if shutil.which(settings.claude_code_binary) is None:
        return {
            "task_id": None,
            "status": "failed",
            "error": (
                f"claude_cli_not_found: '{settings.claude_code_binary}' is not on PATH. "
                "Install Claude Code or set JARVIS_CLAUDE_CODE_BINARY."
            ),
        }

    subpath = inputs.get("subpath", "")
    working_dir = (REPO_ROOT / settings.claude_code_subpath / subpath).resolve()

    if not working_dir.is_relative_to(REPO_ROOT) or not working_dir.is_dir():
        return {
            "task_id": None,
            "status": "failed",
            "error": f"invalid_subpath: '{subpath}' does not resolve to a valid directory inside the repo.",
        }

    task_manager = get_task_manager()
    task_id = task_manager.start(inputs["prompt"], working_dir)
    return {"task_id": task_id, "status": "running", "error": None}
```

`REPO_ROOT` resolves from `apps/core/skills/claude_code_task/skill.py` up 5 levels (`parents[4]`) to the Jarvis OS repo root — verify this by running `.venv/bin/python3 -c "from pathlib import Path; print(Path('skills/claude_code_task/skill.py').resolve().parents[4])"` from `apps/core/` if the path arithmetic is unclear; it should print the `jarvis-os` directory itself.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_claude_code_task_skill.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 108 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add skills/claude_code_task tests/test_claude_code_task_skill.py
git commit -m "feat(skills): add claude_code_task skill"
```

---

### Task 8: Backend endpoints — `GET /tasks/{task_id}` and `GET /tasks`

**Files:**
- Modify: `apps/core/core/app.py`
- Create: `apps/core/tests/test_task_endpoints.py`

**Interfaces:**
- Consumes: `ClaudeCodeTask` (Task 2, already imported into `app.py` in Task 6).
- Produces: `GET /tasks/{task_id}` (full record, 404 if unknown), `GET /tasks` (recent tasks, newest first, limit 50).

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_task_endpoints.py`:
```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import ClaudeCodeTask


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_get_task_returns_404_for_unknown_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/tasks/does-not-exist")

    assert response.status_code == 404


def test_get_task_returns_full_record(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(
            ClaudeCodeTask(
                task_id="abc-123", prompt="do X", working_dir="/tmp", status="completed",
                result_text="Done.", num_turns=2, duration_ms=500, cost_usd=0.02,
            )
        )
        session.commit()

    response = client.get("/tasks/abc-123")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "abc-123"
    assert body["status"] == "completed"
    assert body["result_text"] == "Done."
    assert body["num_turns"] == 2
    assert body["cost_usd"] == 0.02


def test_list_tasks_returns_newest_first(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(ClaudeCodeTask(
            task_id="first", prompt="a", working_dir="/tmp", status="completed",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        session.add(ClaudeCodeTask(
            task_id="second", prompt="b", working_dir="/tmp", status="completed",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ))
        session.commit()

    response = client.get("/tasks")

    assert response.status_code == 200
    body = response.json()
    assert [t["task_id"] for t in body] == ["second", "first"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_task_endpoints.py -v`
Expected: FAIL — 404 Not Found (routes don't exist yet).

- [ ] **Step 3: Add the endpoints**

Read the current contents of `apps/core/core/app.py` first. Add these two routes after the existing `get_voice_audio` route (before `@app.websocket("/ws")`):
```python
    @app.get("/tasks/{task_id}")
    def get_task(task_id: str):
        with app.state.session_factory() as session:
            row = session.get(ClaudeCodeTask, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Task not found")
            return {
                "task_id": row.task_id,
                "status": row.status,
                "prompt": row.prompt,
                "working_dir": row.working_dir,
                "result_text": row.result_text,
                "error": row.error,
                "num_turns": row.num_turns,
                "duration_ms": row.duration_ms,
                "cost_usd": row.cost_usd,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }

    @app.get("/tasks")
    def list_tasks():
        with app.state.session_factory() as session:
            rows = (
                session.query(ClaudeCodeTask)
                .order_by(ClaudeCodeTask.created_at.desc())
                .limit(50)
                .all()
            )
            return [
                {
                    "task_id": row.task_id,
                    "status": row.status,
                    "prompt": row.prompt,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_task_endpoints.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 111 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add core/app.py tests/test_task_endpoints.py
git commit -m "feat(core): add GET /tasks/{id} and GET /tasks endpoints"
```

---

### Task 9: Live contract test

**Files:**
- Create: `apps/core/tests/test_claude_code_cli_contract.py`

**Interfaces:** None new — exercises the real `claude` CLI when present, mirroring the skip-capable pattern from `test_llm_provider_contract.py` (M3) and `test_faster_whisper_contract.py`/`test_piper_contract.py` (M4).

- [ ] **Step 1: Write the contract test**

Create `apps/core/tests/test_claude_code_cli_contract.py`:
```python
import asyncio
import shutil

import pytest

from core.config import Settings
from core.db.database import init_db, make_engine, make_session_factory
from core.events.bus import EventBus
from core.tasks.manager import TaskManager


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_real_claude_cli_completes_a_trivial_task(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    session_factory = make_session_factory(engine)
    settings = Settings(anthropic_api_key=None, claude_code_timeout_seconds=60)
    event_bus = EventBus()
    manager = TaskManager(settings, session_factory, event_bus)
    queue = event_bus.subscribe()

    async def run():
        manager.bind_loop(asyncio.get_running_loop())
        task_id = manager.start("Say the word test and do nothing else. Do not edit any files.", tmp_path)
        events = []
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=60.0)
            events.append(event)
            if event["stage"] in ("completed", "failed", "timed_out"):
                break
        return task_id, events

    task_id, events = asyncio.run(run())

    assert events[-1]["stage"] in ("completed", "failed")

    from core.db.models import ClaudeCodeTask
    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status in ("completed", "failed")
        assert row.finished_at is not None
```

- [ ] **Step 2: Run the contract test to confirm skip behavior**

Run: `.venv/bin/pytest tests/test_claude_code_cli_contract.py -v`
Expected: SKIPPED (unless this environment already has the `claude` CLI installed — if so, it runs for real instead, which is also correct).

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 111 passed, 2 skipped (or 112 collected either way — the new contract test may run for real instead of skipping if `claude` happens to be installed).

- [ ] **Step 4: Commit**

```bash
git add tests/test_claude_code_cli_contract.py
git commit -m "test(core): add live contract test for the real claude CLI"
```

---

### Task 10: End-to-End Manual Smoke Test

**Files:** None (verification only).

**Interfaces:** None — this task exercises the full stack built across Tasks 1-9, including the real `claude` CLI, which the automated suite cannot assume is present.

- [ ] **Step 1: Confirm the Claude Code CLI is installed**

```bash
which claude
claude --version
```
Expected: a path and version print. If not installed, install it per Anthropic's Claude Code installation instructions before continuing, then re-run this step.

- [ ] **Step 2: Start the backend**

```bash
cd apps/core
nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m5-smoke.log 2>&1 &
BACKEND_PID=$!
sleep 3
curl -s http://127.0.0.1:8420/skills | python3 -m json.tool
```
Expected: JSON array including `echo`, `ask`, and `claude_code_task` manifests; the latter shows `"voice_invokable": false` and `"background": true`.

- [ ] **Step 3: Invoke the skill and watch it stream**

In one terminal, connect to the WebSocket and watch events (this requires a small throwaway script since `curl` can't hold a WS connection open):
```bash
.venv/bin/python3 -c "
import asyncio, json, websockets

async def watch():
    async with websockets.connect('ws://127.0.0.1:8420/ws') as ws:
        async for message in ws:
            event = json.loads(message)
            if event.get('type') == 'claude_code_task':
                print(event['stage'], event.get('detail'))
                if event['stage'] in ('completed', 'failed', 'timed_out'):
                    break

asyncio.run(watch())
"
```
Leave this running in the background (or a second terminal), then in another terminal invoke the skill:
```bash
curl -s -X POST http://127.0.0.1:8420/skills/claude_code_task/invoke \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"prompt": "Add a one-line comment to the top of README.md saying Hello from Claude Code, then do not make any other changes."}}'
```
Expected: the invoke call returns immediately (`{"outputs": {"task_id": "...", "status": "running", "error": null}}`), and the WebSocket watcher prints `started`, then `tool_use` (likely `Edit` or `Write` on `README.md`), then `completed` with a `result_excerpt` and `cost_usd`.

- [ ] **Step 4: Confirm the change landed, uncommitted**

```bash
cd /path/to/jarvis-os  # the repo root, not apps/core
git status --short
git diff README.md
```
Expected: `README.md` shows as modified (not committed), and the diff shows the one-line comment was added. This confirms the "no auto-commit" security decision is actually in effect.

- [ ] **Step 5: Confirm the task record via the status endpoint**

```bash
TASK_ID=<the task_id from Step 3's curl response>
curl -s http://127.0.0.1:8420/tasks/$TASK_ID | python3 -m json.tool
curl -s http://127.0.0.1:8420/tasks | python3 -m json.tool
```
Expected: `GET /tasks/{id}` shows `status: "completed"`, a non-null `result_text`, `num_turns`, `duration_ms`, and `cost_usd`. `GET /tasks` includes this task in its list.

- [ ] **Step 6: Revert the test change**

```bash
git checkout README.md
```
Expected: `README.md` reverts to its committed state — confirming `git checkout` is a genuine, working undo path for this milestone's uncommitted-changes model.

- [ ] **Step 7: Test the timeout path**

```bash
kill $BACKEND_PID
JARVIS_CLAUDE_CODE_TIMEOUT_SECONDS=10 nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m5-smoke2.log 2>&1 &
BACKEND_PID=$!
sleep 3
curl -s -X POST http://127.0.0.1:8420/skills/claude_code_task/invoke \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"prompt": "Write a very long, detailed 5000-word essay about the history of computing, taking your time and being thorough."}}'
```
Wait ~15 seconds, then check:
```bash
TASK_ID=<the task_id from the curl response above>
curl -s http://127.0.0.1:8420/tasks/$TASK_ID | python3 -m json.tool
ps aux | grep claude | grep -v grep
```
Expected: the task's status is `"timed_out"` (or `"completed"`/`"failed"` if the CLI genuinely finished within 10 seconds — a fast/short response is also an acceptable outcome, just re-run with a prompt more likely to take longer than 10s if that happens). If timed out: confirm via `ps aux` that no lingering `claude` process (or its child processes) survived past the timeout.

- [ ] **Step 8: Stop the backend**

```bash
kill $BACKEND_PID 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
```

- [ ] **Step 9: Run the full suite one final time**

```bash
cd apps/core && .venv/bin/pytest -v
```
Expected: 111 passed (plus the contract test from Task 9, which will now run for real rather than skip since `claude` is confirmed installed from Step 1 — so likely 112 passed, 0 skipped, or 111 passed + 1 skipped for the Piper contract test from Milestone 4 if Piper is still not working on this machine per that milestone's known issue).

No commit for this task — it's verification only.
