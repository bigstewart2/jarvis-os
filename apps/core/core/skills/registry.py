import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.skills.manifest import ManifestError, SkillManifest, load_manifest


@dataclass
class LoadedSkill:
    manifest: SkillManifest
    run: Callable[[dict], dict]


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, LoadedSkill] = {}

    def load_from_directory(self, skills_dir: Path) -> None:
        if not skills_dir.exists():
            return
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            manifest_path = skill_dir / "manifest.yaml"
            module_path = skill_dir / "skill.py"
            if not manifest_path.exists() or not module_path.exists():
                continue
            manifest = load_manifest(manifest_path)
            run = self._load_run_function(manifest.id, module_path)
            self._skills[manifest.id] = LoadedSkill(manifest=manifest, run=run)

    @staticmethod
    def _load_run_function(skill_id: str, module_path: Path) -> Callable[[dict], dict]:
        spec = importlib.util.spec_from_file_location(f"jarvis_skill_{skill_id}", module_path)
        if spec is None or spec.loader is None:
            raise ManifestError(f"Cannot load skill module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            raise ManifestError(f"Skill '{skill_id}' has no run() function in {module_path}")
        return module.run

    def get(self, skill_id: str) -> LoadedSkill | None:
        return self._skills.get(skill_id)

    def list(self) -> list[SkillManifest]:
        return [loaded.manifest for loaded in self._skills.values()]
