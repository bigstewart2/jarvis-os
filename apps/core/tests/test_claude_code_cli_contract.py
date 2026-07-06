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
