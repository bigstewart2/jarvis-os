import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.automation.registry import AutomationRegistry
from core.automation.runner import AutomationRunner
from core.automation.scheduler import build_scheduler
from core.config import get_settings
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import AutomationRun, ClaudeCodeTask, DashboardConfig
from core.events.bus import EventBus
from core.providers.stt.factory import get_stt_provider
from core.providers.tts.factory import get_tts_provider
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill
from core.skills.registry import SkillRegistry
from core.tasks.manager import TaskManager
from core.tasks.registry import set_task_manager
from core.voice.files import clear_voice_dir
from core.voice.pipeline import run_voice_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent


class InvokeRequest(BaseModel):
    inputs: dict


KNOWN_WIDGET_IDS = {"skills", "voice", "automations", "tasks"}
DEFAULT_WIDGET_ORDER = ["skills", "voice", "automations", "tasks"]


class DashboardConfigRequest(BaseModel):
    widget_order: list[str]
    hidden_widgets: list[str]


def create_app() -> FastAPI:
    app = FastAPI(title="Jarvis OS Core")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "tauri://localhost"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    settings = get_settings()

    registry = SkillRegistry()
    registry.load_from_directory(BASE_DIR / settings.skills_dir)
    app.state.registry = registry

    engine = make_engine(settings.database_url)
    init_db(engine)
    app.state.session_factory = make_session_factory(engine)

    app.state.event_bus = EventBus()

    app.state.stt_provider = get_stt_provider(settings)
    app.state.tts_provider = get_tts_provider(settings)
    clear_voice_dir(BASE_DIR / settings.voice_dir)

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

    @app.get("/skills")
    def list_skills():
        return [manifest.model_dump() for manifest in registry.list()]

    @app.post("/skills/{skill_id}/invoke")
    async def invoke_skill(skill_id: str, request: InvokeRequest):
        try:
            status, outputs = await invoke_and_record_skill(app, skill_id, request.inputs)
        except SkillNotFoundError:
            raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")

        if status == "failed":
            raise HTTPException(status_code=500, detail=outputs)

        return {"outputs": outputs}

    @app.post("/voice/invoke")
    async def voice_invoke(audio: UploadFile = File(...), invocation_id: str = Form(...)):
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio upload")
        extension = Path(audio.filename or "clip.webm").suffix.lstrip(".") or "webm"
        return await run_voice_pipeline(app, audio_bytes, extension, invocation_id)

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

    @app.get("/dashboard/config")
    def get_dashboard_config():
        with app.state.session_factory() as session:
            row = session.query(DashboardConfig).first()
            if row is None:
                row = DashboardConfig(widget_order=DEFAULT_WIDGET_ORDER, hidden_widgets=[])
                session.add(row)
                session.commit()
            return {"widget_order": row.widget_order, "hidden_widgets": row.hidden_widgets}

    @app.put("/dashboard/config")
    def put_dashboard_config(request: DashboardConfigRequest):
        if set(request.widget_order) != KNOWN_WIDGET_IDS or len(request.widget_order) != len(KNOWN_WIDGET_IDS):
            raise HTTPException(
                status_code=400,
                detail=f"widget_order must be exactly a permutation of {sorted(KNOWN_WIDGET_IDS)}",
            )
        if not set(request.hidden_widgets).issubset(KNOWN_WIDGET_IDS):
            raise HTTPException(
                status_code=400,
                detail=f"hidden_widgets must be a subset of {sorted(KNOWN_WIDGET_IDS)}",
            )
        with app.state.session_factory() as session:
            row = session.query(DashboardConfig).first()
            if row is None:
                row = DashboardConfig(widget_order=request.widget_order, hidden_widgets=request.hidden_widgets)
                session.add(row)
            else:
                row.widget_order = request.widget_order
                row.hidden_widgets = request.hidden_widgets
            session.commit()
            return {"widget_order": row.widget_order, "hidden_widgets": row.hidden_widgets}

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

    return app
