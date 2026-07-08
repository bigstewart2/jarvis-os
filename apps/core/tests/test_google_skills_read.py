from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load(skill_id):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    return registry.get(skill_id)


def test_get_calendar_events_manifest_is_voice_invokable():
    loaded = _load("get_calendar_events")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is True


def test_search_email_manifest_is_voice_invokable():
    loaded = _load("search_email")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is True


def test_get_calendar_events_run_returns_events(monkeypatch):
    loaded = _load("get_calendar_events")

    class FakeCalendarClient:
        def list_events(self, days_ahead=1):
            assert days_ahead == 3
            return [{"title": "Interview", "start": "s", "end": "e", "location": "", "attendee_count": 1}]

    monkeypatch.setitem(loaded.run.__globals__, "_build_calendar_client", lambda: FakeCalendarClient())

    result = loaded.run({"days_ahead": 3})

    assert result == {"events": [{"title": "Interview", "start": "s", "end": "e", "location": "", "attendee_count": 1}]}


def test_get_calendar_events_defaults_days_ahead_to_one(monkeypatch):
    loaded = _load("get_calendar_events")

    class FakeCalendarClient:
        def list_events(self, days_ahead=1):
            assert days_ahead == 1
            return []

    monkeypatch.setitem(loaded.run.__globals__, "_build_calendar_client", lambda: FakeCalendarClient())

    assert loaded.run({}) == {"events": []}


def test_search_email_run_returns_messages(monkeypatch):
    loaded = _load("search_email")

    class FakeGmailClient:
        def search_messages(self, query, limit=10):
            assert query == "from:recruiter"
            return [{"from_": "r@x.com", "subject": "Role", "date": "d", "snippet": "s"}]

    monkeypatch.setitem(loaded.run.__globals__, "_build_gmail_client", lambda: FakeGmailClient())

    result = loaded.run({"query": "from:recruiter"})

    assert result == {"messages": [{"from_": "r@x.com", "subject": "Role", "date": "d", "snippet": "s"}]}
