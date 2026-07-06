from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def test_manifest_is_not_voice_invokable_and_is_background():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("claude_code_task")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False
    assert loaded.manifest.background is True


def test_run_returns_failed_status_when_cli_missing(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type(
        "FakeSettings", (), {"claude_code_binary": "definitely-not-a-real-binary-xyz", "claude_code_subpath": ""}
    )()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    result = loaded.run({"prompt": "do something"})

    assert result["task_id"] is None
    assert result["status"] == "failed"
    assert "claude_cli_not_found" in result["error"]


def test_run_returns_failed_status_for_subpath_escaping_repo(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type("FakeSettings", (), {"claude_code_binary": "python3", "claude_code_subpath": ""})()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    result = loaded.run({"prompt": "do something", "subpath": "../../etc"})

    assert result["task_id"] is None
    assert result["status"] == "failed"
    assert "invalid_subpath" in result["error"]


def test_run_starts_a_task_and_returns_running(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("claude_code_task")

    fake_settings = type("FakeSettings", (), {"claude_code_binary": "python3", "claude_code_subpath": ""})()
    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: fake_settings)

    class FakeTaskManager:
        def start(self, prompt, working_dir):
            assert prompt == "do something"
            return "fake-task-id"

    monkeypatch.setitem(loaded.run.__globals__, "get_task_manager", lambda: FakeTaskManager())

    result = loaded.run({"prompt": "do something"})

    assert result == {"task_id": "fake-task-id", "status": "running", "error": None}
