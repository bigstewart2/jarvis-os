import asyncio

import pytest

from core.app import create_app
from core.db.models import SkillInvocation
from core.skills.invocation import SkillNotFoundError, invoke_and_record_skill


def test_invoke_and_record_skill_returns_completed_status_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    status, outputs = asyncio.run(invoke_and_record_skill(app, "echo", {"text": "hi"}))

    assert status == "completed"
    assert outputs == {"text": "hi"}

    with app.state.session_factory() as session:
        row = session.query(SkillInvocation).filter_by(skill_id="echo").one()
        assert row.status == "completed"
        assert row.outputs == {"text": "hi"}


def test_invoke_and_record_skill_raises_for_unknown_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()

    with pytest.raises(SkillNotFoundError):
        asyncio.run(invoke_and_record_skill(app, "does-not-exist", {}))
