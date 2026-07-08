from core.providers.google.calendar import GoogleCalendarClient


class FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeEvents:
    def __init__(self, list_result=None):
        self._list_result = list_result or {}
        self.list_kwargs = None
        self.insert_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return FakeExecutable(self._list_result)

    def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        return FakeExecutable({
            "id": "evt-123",
            "htmlLink": "https://calendar.google.com/event?eid=abc",
            "summary": kwargs["body"]["summary"],
            "start": kwargs["body"]["start"],
            "end": kwargs["body"]["end"],
        })


class FakeService:
    def __init__(self, events):
        self._events = events

    def events(self):
        return self._events


def test_list_events_normalizes_and_requests_correct_window():
    fake_events = FakeEvents(list_result={
        "items": [
            {
                "summary": "Interview with Valence",
                "start": {"dateTime": "2026-07-08T13:00:00-04:00"},
                "end": {"dateTime": "2026-07-08T14:00:00-04:00"},
                "location": "Google Meet",
                "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}],
            },
            {
                "summary": "All-day thing",
                "start": {"date": "2026-07-08"},
                "end": {"date": "2026-07-09"},
            },
        ]
    })
    client = GoogleCalendarClient(FakeService(fake_events))

    events = client.list_events(days_ahead=2)

    assert fake_events.list_kwargs["calendarId"] == "primary"
    assert fake_events.list_kwargs["singleEvents"] is True
    assert fake_events.list_kwargs["orderBy"] == "startTime"
    assert events == [
        {
            "title": "Interview with Valence",
            "start": "2026-07-08T13:00:00-04:00",
            "end": "2026-07-08T14:00:00-04:00",
            "location": "Google Meet",
            "attendee_count": 2,
        },
        {
            "title": "All-day thing",
            "start": "2026-07-08",
            "end": "2026-07-09",
            "location": "",
            "attendee_count": 0,
        },
    ]


def test_list_events_returns_empty_list_when_no_items():
    client = GoogleCalendarClient(FakeService(FakeEvents(list_result={})))

    assert client.list_events() == []


def test_create_event_builds_correct_body_and_normalizes_response():
    fake_events = FakeEvents()
    client = GoogleCalendarClient(FakeService(fake_events))

    created = client.create_event(
        title="Coffee with Sam",
        start_iso="2026-07-10T15:00:00-04:00",
        end_iso="2026-07-10T15:30:00-04:00",
        description="Catch up",
    )

    body = fake_events.insert_kwargs["body"]
    assert fake_events.insert_kwargs["calendarId"] == "primary"
    assert body["summary"] == "Coffee with Sam"
    assert body["description"] == "Catch up"
    assert body["start"] == {"dateTime": "2026-07-10T15:00:00-04:00"}
    assert body["end"] == {"dateTime": "2026-07-10T15:30:00-04:00"}
    assert created["event_id"] == "evt-123"
    assert created["html_link"].startswith("https://calendar.google.com/")
    assert created["title"] == "Coffee with Sam"
