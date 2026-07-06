from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import get_settings
from core.db.database import init_db, make_engine, make_session_factory
from core.db.models import SkillInvocation
from core.events.bus import EventBus
from core.providers.stt.factory import get_stt_provider
from core.providers.tts.factory import get_tts_provider
from core.skills.registry import SkillRegistry

BASE_DIR = Path(__file__).resolve().parent.parent


class InvokeRequest(BaseModel):
    inputs: dict


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
