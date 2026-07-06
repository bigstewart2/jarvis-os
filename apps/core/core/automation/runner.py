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
        self._background_tasks: set[asyncio.Task] = set()

    def _spawn_run(self, automation_id: str, trigger: str) -> tuple[str, asyncio.Task]:
        run_id = str(uuid.uuid4())
        with self._app.state.session_factory() as session:
            session.add(
                AutomationRun(
                    run_id=run_id, automation_id=automation_id, trigger=trigger, status="running", steps=[]
                )
            )
            session.commit()

        task = asyncio.create_task(self._run(run_id, automation_id, trigger))
        # Keep a strong reference: the event loop only holds a weak reference
        # to scheduled tasks, so an unreferenced task can be garbage-collected
        # mid-run. Discard it from the set once it finishes.
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return run_id, task

    async def start(self, automation_id: str, trigger: str) -> str:
        """Kick off a run without waiting for it to finish.

        Used by the manual-trigger HTTP endpoint, which must return
        immediately (202 Accepted) regardless of how long the run takes.
        """
        run_id, _task = self._spawn_run(automation_id, trigger)
        return run_id

    async def run_and_wait(self, automation_id: str, trigger: str) -> str:
        """Run an automation and block until it finishes.

        Used by the scheduler for cron-triggered runs so that APScheduler's
        `max_instances=1` can actually prevent overlapping runs of the same
        automation: unlike `start()`, this coroutine does not return to
        APScheduler until the run is complete, so a second cron firing while
        this one is still in flight is recognized as a real overlap.
        """
        run_id, task = self._spawn_run(automation_id, trigger)
        await task
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
        # Contract: every run must reach exactly one terminal DB state
        # ("completed" or "failed"), written before the corresponding event
        # is published. The outer `except Exception` below is the backstop
        # for any unexpected error in lookup or any step. asyncio.CancelledError
        # is deliberately NOT caught here: a run cancelled that way (e.g. app
        # shutdown) is instead swept up as "interrupted" by the startup-time
        # stale-run sweep in app.py, not by this function.
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
            self._write_terminal_state(run_id, "completed")
            await self._publish(
                run_id, automation_id, "completed", {"result_excerpt": result_excerpt, "audio_url": audio_url}
            )
        except Exception as exc:  # noqa: BLE001 - top-level guard so a run can never be stuck "running"
            error_message = f"{type(exc).__name__}: {exc}"
            self._write_terminal_state(run_id, "failed", error=error_message)
            await self._publish(run_id, automation_id, "failed", {"error": error_message})
