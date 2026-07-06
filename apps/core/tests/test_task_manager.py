import asyncio
import os
import time
from pathlib import Path

import pytest

import core.tasks.manager as manager_module
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


def test_subprocess_spawn_failure_marks_task_failed_not_stuck_running(tmp_path, monkeypatch):
    """Finding 1: if create_subprocess_exec itself raises (binary vanished,
    OSError under fork/exec contention, etc.), the task must not be left
    stuck in "running" forever with no diagnostic trace."""

    async def _raise_oserror(*args, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(manager_module.asyncio, "create_subprocess_exec", _raise_oserror)

    manager, session_factory, event_bus = _make_manager(tmp_path)

    task_id, events = asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    assert events[-1]["stage"] == "failed"
    assert "exec failed" in events[-1]["detail"]["error"]

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status == "failed"
        assert row.status != "running"
        assert row.error is not None


def test_large_stream_json_line_does_not_break_task(tmp_path, monkeypatch):
    """Finding 2: real Claude Code stream-json output can emit lines well
    over asyncio's default 64KB readline() limit (e.g. large tool results).
    Without the `limit=` bump on create_subprocess_exec, this line would
    raise ValueError inside read_stdout() and (per Finding 1) leave the task
    stuck in "running" forever."""
    monkeypatch.setenv("STUB_CLI_MODE", "large_line")
    manager, session_factory, event_bus = _make_manager(tmp_path)

    task_id, events = asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    assert events[-1]["stage"] == "completed"

    with session_factory() as session:
        row = session.get(ClaudeCodeTask, task_id)
        assert row.status == "completed"


def test_argv_includes_allowed_tools_and_excludes_dangerous_flag(tmp_path, monkeypatch):
    """Finding 4: assert the actual argv passed to the subprocess includes
    --allowedTools with the configured value, and never includes
    --dangerously-skip-permissions."""
    captured: dict = {}
    real_create_subprocess_exec = manager_module.asyncio.create_subprocess_exec

    async def _spy_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return await real_create_subprocess_exec(*args, **kwargs)

    monkeypatch.setattr(manager_module.asyncio, "create_subprocess_exec", _spy_create_subprocess_exec)
    monkeypatch.setenv("STUB_CLI_MODE", "success")

    manager, session_factory, event_bus = _make_manager(tmp_path)
    asyncio.run(_run_and_collect_events(manager, event_bus, tmp_path))

    argv = captured["args"]
    assert "--dangerously-skip-permissions" not in argv

    assert "--allowedTools" in argv
    idx = argv.index("--allowedTools")
    assert argv[idx + 1] == manager._settings.claude_code_allowed_tools
