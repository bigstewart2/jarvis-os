from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load(skill_id):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    return registry.get(skill_id)


def test_draft_email_manifest_is_not_voice_invokable():
    loaded = _load("draft_email")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_create_calendar_event_manifest_is_not_voice_invokable():
    loaded = _load("create_calendar_event")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_draft_email_run_creates_draft(monkeypatch):
    loaded = _load("draft_email")

    class FakeGmailClient:
        def create_draft(self, to, subject, body):
            assert to == "r@x.com"
            assert subject == "Hello"
            assert body == "Body text"
            return {"draft_id": "d1", "to": to, "subject": subject}

    monkeypatch.setitem(loaded.run.__globals__, "_build_gmail_client", lambda: FakeGmailClient())

    result = loaded.run({"to": "r@x.com", "subject": "Hello", "body": "Body text"})

    assert result == {"draft_id": "d1", "to": "r@x.com", "subject": "Hello"}


def test_create_calendar_event_run_creates_event(monkeypatch):
    loaded = _load("create_calendar_event")

    class FakeCalendarClient:
        def create_event(self, title, start_iso, end_iso, description=""):
            assert title == "Coffee"
            assert description == ""
            return {"event_id": "e1", "html_link": "https://cal", "title": title, "start": start_iso, "end": end_iso}

    monkeypatch.setitem(loaded.run.__globals__, "_build_calendar_client", lambda: FakeCalendarClient())

    result = loaded.run({"title": "Coffee", "start_iso": "2026-07-10T15:00:00-04:00", "end_iso": "2026-07-10T15:30:00-04:00"})

    assert result["event_id"] == "e1"
    assert result["title"] == "Coffee"
