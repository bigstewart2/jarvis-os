import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.config import get_settings
from core.db.database import init_db, make_engine, make_session_factory
from core.events.bus import EventBus
from core.providers.stt.factory import get_stt_provider
from core.providers.tts.factory import get_tts_provider
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill
from core.skills.registry import SkillRegistry
from core.voice.files import clear_voice_dir
from core.voice.pipeline import run_voice_pipeline

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
    clear_voice_dir(BASE_DIR / settings.voice_dir)

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
