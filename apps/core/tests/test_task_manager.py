import asyncio
import os
import time
from pathlib import Path

import pytest

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
