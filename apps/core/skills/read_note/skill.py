from pathlib import Path

from core.config import get_settings
from core.providers.knowledge.obsidian import ObsidianVaultSource

BASE_DIR = Path(__file__).resolve().parents[2]


def run(inputs: dict) -> dict:
    settings = get_settings()
    vault_root = BASE_DIR / settings.knowledge_vault_dir
    source = ObsidianVaultSource(vault_root)
    content = source.read(inputs["path"])
    return {"content": content}
