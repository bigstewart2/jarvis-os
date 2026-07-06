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
