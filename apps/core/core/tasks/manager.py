import asyncio
import logging
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.config import Settings
from core.db.models import ClaudeCodeTask
from core.events.bus import EventBus
from core.tasks.stream import parse_stream_line

logger = logging.getLogger(__name__)

# Default asyncio stream-reader line limit is 64KB, which real Claude Code
# `stream-json` output (e.g. `type: "user"` tool-result lines) can easily
# exceed. Use a generous limit so a long line raises well before that.
_STREAM_LIMIT_BYTES = 10 * 1024 * 1024


class TaskManager:
    def __init__(self, settings: Settings, session_factory, event_bus: EventBus) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self, prompt: str, working_dir: Path) -> str:
        if self._loop is None:
            raise RuntimeError("TaskManager.bind_loop() must be called before start()")

        task_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                ClaudeCodeTask(task_id=task_id, prompt=prompt, working_dir=str(working_dir), status="running")
            )
            session.commit()

        future = asyncio.run_coroutine_threadsafe(self._run(task_id, prompt, working_dir), self._loop)

        def _log_unhandled_exception(fut: "asyncio.Future") -> None:
            try:
                exc = fut.exception()
            except asyncio.CancelledError:
                return
            if exc is not None:
                logger.error("TaskManager._run(task_id=%s) raised an unhandled exception", task_id, exc_info=exc)

        future.add_done_callback(_log_unhandled_exception)
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

    async def _run(self, task_id: str, prompt: str, working_dir: Path) -> None:
        process: asyncio.subprocess.Process | None = None
        try:
            await self._publish(task_id, "started", {"prompt_excerpt": prompt[:120], "working_dir": str(working_dir)})

            process = await asyncio.create_subprocess_exec(
                self._settings.claude_code_binary,
                "-p", prompt,
                "--output-format", "stream-json",
                "--verbose",
                "--allowedTools", self._settings.claude_code_allowed_tools,
                "--max-turns", str(self._settings.claude_code_max_turns),
                cwd=str(working_dir),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                limit=_STREAM_LIMIT_BYTES,
            )

            result_detail: dict = {}
            stderr_chunks: list[bytes] = []

            async def read_stdout() -> None:
                assert process is not None
                assert process.stdout is not None
                while True:
                    raw_line = await process.stdout.readline()
                    if not raw_line:
                        break
                    decoded_line = raw_line.decode("utf-8", errors="replace")
                    event = parse_stream_line(decoded_line)
                    if event is None:
                        if decoded_line.strip():
                            logger.warning(
                                "task_id=%s: failed to parse stream-json line: %s",
                                task_id,
                                decoded_line.strip()[:200],
                            )
                        continue
                    if event.stage == "result":
                        result_detail.update(event.detail)
                    else:
                        await self._publish(task_id, event.stage, event.detail)

            async def read_stderr() -> None:
                assert process is not None
                assert process.stderr is not None
                while True:
                    chunk = await process.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

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
        except Exception as exc:  # noqa: BLE001 - top-level guard so a task can never be stuck "running"
            logger.error("task_id=%s: _run() failed with an unhandled exception", task_id, exc_info=exc)
            if process is not None:
                try:
                    await self._kill_process_group(process)
                except Exception:  # noqa: BLE001 - best-effort cleanup, must not mask the original error
                    logger.exception("task_id=%s: failed to kill process group during error cleanup", task_id)
            error_message = f"{type(exc).__name__}: {exc}"
            await self._publish(task_id, "failed", {"error": error_message})
            self._write_terminal_state(task_id, "failed", error=error_message)
