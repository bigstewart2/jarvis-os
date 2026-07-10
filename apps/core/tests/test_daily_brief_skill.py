import json
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    return registry.get("daily_brief")


class FakeCalendarClient:
    def __init__(self, events=None, error=None):
        self._events = events or []
        self._error = error

    def list_events(self, days_ahead=1):
        if self._error:
            raise self._error
        return self._events


class FakeGmailClient:
    def __init__(self, messages=None, error=None):
        self._messages = messages or []
        self._error = error

    def search_messages(self, query, limit=10):
        if self._error:
            raise self._error
        return self._messages


class FakeLLM:
    def __init__(self):
        self.prompt = None
        self.system = None

    def complete(self, prompt, *, system=None):
        self.prompt = prompt
        self.system = system
        return "Good morning. Light day ahead.\n"


def _patch(loaded, monkeypatch, calendar, gmail, llm):
    monkeypatch.setitem(loaded.run.__globals__, "_build_calendar_client", lambda: calendar)
    monkeypatch.setitem(loaded.run.__globals__, "_build_gmail_client", lambda: gmail)
    monkeypatch.setitem(loaded.run.__globals__, "get_llm_provider", lambda settings: llm)


def test_manifest_is_voice_invokable_with_no_required_inputs():
    loaded = _load()

    assert loaded is not None
    assert loaded.manifest.voice_invokable is True
    assert loaded.manifest.input_schema.get("required") in (None, [])


def test_run_composes_brief_from_calendar_and_email(monkeypatch):
    loaded = _load()
    events = [{"title": "Standup", "start": "s", "end": "e", "location": "", "attendee_count": 3}]
    messages = [{"from_": "a@b.com", "subject": "Offer", "date": "d", "snippet": "hi"}]
    llm = FakeLLM()
    _patch(loaded, monkeypatch, FakeCalendarClient(events), FakeGmailClient(messages), llm)

    result = loaded.run({})

    assert result["brief"] == "Good morning. Light day ahead."
    assert result["events"] == events
    assert result["messages"] == messages
    payload = json.loads(llm.prompt)
    assert payload["calendar_events"] == events
    assert payload["recent_emails"] == messages
    assert payload["source_errors"] == []
    assert "Jarvis" in llm.system


def test_run_survives_source_failures_and_reports_them_to_the_llm(monkeypatch):
    loaded = _load()
    llm = FakeLLM()
    _patch(
        loaded,
        monkeypatch,
        FakeCalendarClient(error=RuntimeError("no token")),
        FakeGmailClient(error=RuntimeError("quota")),
        llm,
    )

    result = loaded.run({})

    assert result["brief"] == "Good morning. Light day ahead."
    assert result["events"] == []
    assert result["messages"] == []
    payload = json.loads(llm.prompt)
    assert len(payload["source_errors"]) == 2


def test_run_passes_custom_inputs_through(monkeypatch):
    loaded = _load()

    class AssertingCalendar(FakeCalendarClient):
        def list_events(self, days_ahead=1):
            assert days_ahead == 3
            return []

    class AssertingGmail(FakeGmailClient):
        def search_messages(self, query, limit=10):
            assert query == "from:recruiter"
            return []

    _patch(loaded, monkeypatch, AssertingCalendar(), AssertingGmail(), FakeLLM())

    loaded.run({"days_ahead": 3, "email_query": "from:recruiter"})
