from pathlib import Path

from fastapi import FastAPI

from core.config import get_settings
from core.skills.registry import SkillRegistry

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="Jarvis OS Core")
    settings = get_settings()

    registry = SkillRegistry()
    registry.load_from_directory(BASE_DIR / settings.skills_dir)
    app.state.registry = registry

    @app.get("/skills")
    def list_skills():
        return [manifest.model_dump() for manifest in registry.list()]

    return app
