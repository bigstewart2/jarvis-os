# Jarvis OS Milestone 8b: Google Calendar & Gmail Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four new skills backed by real Google APIs — `get_calendar_events`, `search_email` (both voice-invokable, read-only) and `draft_email`, `create_calendar_event` (UI-only writes) — behind a `core/providers/google/` package.

**Architecture:** `auth.py` loads/refreshes/persists the OAuth token (already granted, lives at `apps/core/google_token.json`, gitignored). `GoogleCalendarClient` and `GmailClient` wrap `googleapiclient` service objects and normalize responses to plain dicts. Skills follow the exact `search_notes`/`read_note` pattern (BASE_DIR + `get_settings()` + provider construction inside `run()`).

**Tech Stack:** `google-auth`, `google-auth-oauthlib`, `google-api-python-client` (new deps, already installed in the dev venv). Python 3.12+, existing skill system, no frontend changes.

## Global Constraints

- Gmail scope is `gmail.compose` — drafts only, NEVER `gmail.send`. No skill may send email. This is a security boundary from the spec, not a preference.
- `draft_email` and `create_calendar_event` manifests MUST have `voice_invokable: false`. `get_calendar_events` and `search_email` have `voice_invokable: true`.
- New `Settings` fields (exact): `google_credentials_path: str = "google_credentials.json"`, `google_token_path: str = "google_token.json"`.
- Token/credentials files are gitignored (already done, verify before any commit: `git status` must never show `google_credentials.json`/`google_token.json`).
- Skill outputs must never contain the token or credentials content.
- Unit tests never call real Google APIs. Live contract tests are `skipif`-guarded on the token file existing (pattern: `tests/test_piper_contract.py`).
- No new frontend work this milestone — the auto-rendered skill cards are the UI.

---

### Task 1: Config fields, `GoogleAuthError`, `auth.py`, re-auth script

**Files:**
- Modify: `apps/core/core/config.py` (two new fields after `knowledge_vault_dir`)
- Create: `apps/core/core/providers/google/__init__.py` (empty)
- Create: `apps/core/core/providers/google/auth.py`
- Create: `apps/core/scripts/google_oauth_setup.py`
- Test: `apps/core/tests/test_google_auth.py`

**Interfaces:**
- Produces: `get_google_credentials(settings) -> google.oauth2.credentials.Credentials` (loads token relative to BASE_DIR, refreshes+persists if expired, raises `GoogleAuthError` if missing/unusable); `GoogleAuthError(Exception)`; `GOOGLE_SCOPES` list constant.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_google_auth.py`:

```python
import json

import pytest

from core.providers.google.auth import GoogleAuthError, get_google_credentials

VALID_TOKEN = {
    "token": "fake-access-token",
    "refresh_token": "fake-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "fake-client-id",
    "client_secret": "fake-client-secret",
    "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
    "expiry": "2099-01-01T00:00:00Z",
}


class FakeSettings:
    def __init__(self, token_path):
        self.google_token_path = str(token_path)
        self.google_credentials_path = "unused-credentials.json"


def test_returns_credentials_from_valid_token_file(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(VALID_TOKEN))

    creds = get_google_credentials(FakeSettings(token_path))

    assert creds.token == "fake-access-token"
    assert creds.valid


def test_raises_google_auth_error_when_token_missing(tmp_path):
    with pytest.raises(GoogleAuthError, match="google_oauth_setup"):
        get_google_credentials(FakeSettings(tmp_path / "does-not-exist.json"))


def test_refreshes_and_persists_expired_token(tmp_path, monkeypatch):
    expired = dict(VALID_TOKEN, expiry="2020-01-01T00:00:00Z")
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(expired))

    def fake_refresh(self, request):
        self.token = "refreshed-access-token"
        import datetime
        self.expiry = datetime.datetime(2099, 1, 1)

    monkeypatch.setattr("google.oauth2.credentials.Credentials.refresh", fake_refresh)

    creds = get_google_credentials(FakeSettings(token_path))

    assert creds.token == "refreshed-access-token"
    persisted = json.loads(token_path.read_text())
    assert persisted["token"] == "refreshed-access-token"


def test_raises_google_auth_error_for_expired_token_without_refresh_token(tmp_path):
    broken = dict(VALID_TOKEN, expiry="2020-01-01T00:00:00Z")
    del broken["refresh_token"]
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(broken))

    with pytest.raises(GoogleAuthError, match="google_oauth_setup"):
        get_google_credentials(FakeSettings(token_path))
```

Note for the implementer: `FakeSettings.google_token_path` is an ABSOLUTE path (`tmp_path`), and `auth.py` joins it as `BASE_DIR / settings.google_token_path` — pathlib's join discards the left side when the right is absolute (same trick `test_search_notes_skill.py` documents and relies on), so no BASE_DIR mocking is needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.providers.google'`

- [ ] **Step 3: Write minimal implementation**

Add to `apps/core/core/config.py`, immediately after the `knowledge_vault_dir` line:

```python
    google_credentials_path: str = "google_credentials.json"
    google_token_path: str = "google_token.json"
```

Create `apps/core/core/providers/google/__init__.py` (empty).

Create `apps/core/core/providers/google/auth.py`:

```python
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

BASE_DIR = Path(__file__).resolve().parents[3]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

_REAUTH_HINT = (
    "Google token missing or unusable. Re-run the consent flow: "
    "cd apps/core && .venv/bin/python scripts/google_oauth_setup.py"
)


class GoogleAuthError(Exception):
    pass


def get_google_credentials(settings) -> Credentials:
    token_path = BASE_DIR / settings.google_token_path
    if not token_path.exists():
        raise GoogleAuthError(_REAUTH_HINT)

    creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            raise GoogleAuthError(_REAUTH_HINT)

    return creds
```

Create `apps/core/scripts/google_oauth_setup.py` (preserving the exact flow used live on 2026-07-07):

```python
"""One-time OAuth consent flow for Jarvis OS.

Opens a browser for Google consent and saves google_token.json next to
google_credentials.json. Run from apps/core:

    .venv/bin/python scripts/google_oauth_setup.py
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from core.providers.google.auth import GOOGLE_SCOPES

BASE_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(BASE_DIR / "google_credentials.json"), GOOGLE_SCOPES
    )
    creds = flow.run_local_server(port=0)
    (BASE_DIR / "google_token.json").write_text(creds.to_json())
    print("Token saved with scopes:", creds.scopes)


if __name__ == "__main__":
    main()
```

Add the three dependencies to `apps/core/requirements.txt` (append after the `apscheduler` line):

```
google-auth>=2.0
google-auth-oauthlib>=1.0
google-api-python-client>=2.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_auth.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git status   # MUST NOT list google_credentials.json or google_token.json
git add apps/core/core/config.py apps/core/core/providers/google/ apps/core/scripts/google_oauth_setup.py apps/core/requirements.txt apps/core/tests/test_google_auth.py
git commit -m "feat(core): add Google OAuth auth module, config, and re-auth script"
```

---

### Task 2: `GoogleCalendarClient`

**Files:**
- Create: `apps/core/core/providers/google/calendar.py`
- Test: `apps/core/tests/test_google_calendar.py`

**Interfaces:**
- Consumes: a `googleapiclient` service object (constructed by callers via `build("calendar", "v3", credentials=...)`; the client takes the service as a constructor arg so tests inject a fake).
- Produces: `GoogleCalendarClient(service)` with `list_events(days_ahead: int = 1) -> list[dict]` (each: `title`, `start`, `end`, `location`, `attendee_count`) and `create_event(title: str, start_iso: str, end_iso: str, description: str = "") -> dict` (`event_id`, `html_link`, `title`, `start`, `end`).

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_google_calendar.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_calendar.py -v`
Expected: FAIL with `ImportError` (no `calendar` module yet)

- [ ] **Step 3: Write minimal implementation**

Create `apps/core/core/providers/google/calendar.py`:

```python
from datetime import datetime, timedelta, timezone


class GoogleCalendarClient:
    def __init__(self, service):
        self._service = service

    def list_events(self, days_ahead: int = 1) -> list[dict]:
        now = datetime.now(timezone.utc)
        response = self._service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days_ahead)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=25,
        ).execute()

        events = []
        for item in response.get("items", []):
            events.append({
                "title": item.get("summary", "(no title)"),
                "start": item["start"].get("dateTime", item["start"].get("date", "")),
                "end": item["end"].get("dateTime", item["end"].get("date", "")),
                "location": item.get("location", ""),
                "attendee_count": len(item.get("attendees", [])),
            })
        return events

    def create_event(self, title: str, start_iso: str, end_iso: str, description: str = "") -> dict:
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        created = self._service.events().insert(calendarId="primary", body=body).execute()
        return {
            "event_id": created["id"],
            "html_link": created.get("htmlLink", ""),
            "title": created.get("summary", title),
            "start": created.get("start", {}).get("dateTime", start_iso),
            "end": created.get("end", {}).get("dateTime", end_iso),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_calendar.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/providers/google/calendar.py apps/core/tests/test_google_calendar.py
git commit -m "feat(core): add GoogleCalendarClient (list + create events)"
```

---

### Task 3: `GmailClient`

**Files:**
- Create: `apps/core/core/providers/google/gmail.py`
- Test: `apps/core/tests/test_google_gmail.py`

**Interfaces:**
- Produces: `GmailClient(service)` with `search_messages(query: str, limit: int = 10) -> list[dict]` (each: `from_`, `subject`, `date`, `snippet`) and `create_draft(to: str, subject: str, body: str) -> dict` (`draft_id`, `to`, `subject`).

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_google_gmail.py`:

```python
import base64
from email import message_from_bytes

from core.providers.google.gmail import GmailClient


class FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeMessages:
    def __init__(self):
        self.list_kwargs = None
        self.get_calls = []

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return FakeExecutable({"messages": [{"id": "m1"}, {"id": "m2"}]})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        msg_id = kwargs["id"]
        return FakeExecutable({
            "id": msg_id,
            "snippet": f"snippet for {msg_id}",
            "payload": {
                "headers": [
                    {"name": "From", "value": f"sender-{msg_id}@example.com"},
                    {"name": "Subject", "value": f"Subject {msg_id}"},
                    {"name": "Date", "value": "Tue, 7 Jul 2026 10:00:00 -0400"},
                ]
            },
        })


class FakeDrafts:
    def __init__(self):
        self.create_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return FakeExecutable({"id": "draft-99"})


class FakeUsers:
    def __init__(self, messages, drafts):
        self._messages = messages
        self._drafts = drafts

    def messages(self):
        return self._messages

    def drafts(self):
        return self._drafts


class FakeService:
    def __init__(self, messages=None, drafts=None):
        self._users = FakeUsers(messages or FakeMessages(), drafts or FakeDrafts())

    def users(self):
        return self._users


def test_search_messages_normalizes_headers_and_passes_query():
    fake_messages = FakeMessages()
    client = GmailClient(FakeService(messages=fake_messages))

    results = client.search_messages("from:recruiter newer_than:7d", limit=2)

    assert fake_messages.list_kwargs["userId"] == "me"
    assert fake_messages.list_kwargs["q"] == "from:recruiter newer_than:7d"
    assert fake_messages.list_kwargs["maxResults"] == 2
    assert results == [
        {
            "from_": "sender-m1@example.com",
            "subject": "Subject m1",
            "date": "Tue, 7 Jul 2026 10:00:00 -0400",
            "snippet": "snippet for m1",
        },
        {
            "from_": "sender-m2@example.com",
            "subject": "Subject m2",
            "date": "Tue, 7 Jul 2026 10:00:00 -0400",
            "snippet": "snippet for m2",
        },
    ]


def test_search_messages_returns_empty_for_no_matches():
    fake_messages = FakeMessages()
    fake_messages.list = lambda **kwargs: FakeExecutable({})
    client = GmailClient(FakeService(messages=fake_messages))

    assert client.search_messages("nothing") == []


def test_create_draft_builds_rfc822_message():
    fake_drafts = FakeDrafts()
    client = GmailClient(FakeService(drafts=fake_drafts))

    created = client.create_draft(
        to="recruiter@example.com",
        subject="Following up",
        body="Hi — just following up on our conversation.",
    )

    assert created == {"draft_id": "draft-99", "to": "recruiter@example.com", "subject": "Following up"}
    raw = fake_drafts.create_kwargs["body"]["message"]["raw"]
    decoded = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert decoded["To"] == "recruiter@example.com"
    assert decoded["Subject"] == "Following up"
    assert "following up on our conversation" in decoded.get_payload()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_gmail.py -v`
Expected: FAIL with `ImportError` (no `gmail` module yet)

- [ ] **Step 3: Write minimal implementation**

Create `apps/core/core/providers/google/gmail.py`:

```python
import base64
from email.message import EmailMessage


class GmailClient:
    def __init__(self, service):
        self._service = service

    def search_messages(self, query: str, limit: int = 10) -> list[dict]:
        listing = self._service.users().messages().list(
            userId="me", q=query, maxResults=limit
        ).execute()

        results = []
        for ref in listing.get("messages", []):
            full = self._service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            results.append({
                "from_": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return results

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        created = self._service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        return {"draft_id": created["id"], "to": to, "subject": subject}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_gmail.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/providers/google/gmail.py apps/core/tests/test_google_gmail.py
git commit -m "feat(core): add GmailClient (search + create drafts, no send)"
```

---

### Task 4: Read-only skills — `get_calendar_events` + `search_email`

**Files:**
- Create: `apps/core/skills/get_calendar_events/manifest.yaml`
- Create: `apps/core/skills/get_calendar_events/skill.py`
- Create: `apps/core/skills/search_email/manifest.yaml`
- Create: `apps/core/skills/search_email/skill.py`
- Test: `apps/core/tests/test_google_skills_read.py`

**Interfaces:**
- Consumes: `get_google_credentials` (Task 1), `GoogleCalendarClient` (Task 2), `GmailClient` (Task 3), `googleapiclient.discovery.build`.
- Produces: `get_calendar_events.run({"days_ahead": int?}) -> {"events": [...]}`; `search_email.run({"query": str}) -> {"messages": [...]}`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_google_skills_read.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_skills_read.py -v`
Expected: FAIL — `loaded is None` (skills don't exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `apps/core/skills/get_calendar_events/manifest.yaml`:

```yaml
id: get_calendar_events
name: Get Calendar Events
description: Lists upcoming events from your Google Calendar for the next N days (default 1).
voice_invokable: true
input_schema:
  type: object
  properties:
    days_ahead:
      type: integer
output_schema:
  type: object
  properties:
    events:
      type: array
```

Create `apps/core/skills/get_calendar_events/skill.py`:

```python
from googleapiclient.discovery import build

from core.config import get_settings
from core.providers.google.auth import get_google_credentials
from core.providers.google.calendar import GoogleCalendarClient


def _build_calendar_client() -> GoogleCalendarClient:
    creds = get_google_credentials(get_settings())
    service = build("calendar", "v3", credentials=creds)
    return GoogleCalendarClient(service)


def run(inputs: dict) -> dict:
    days_ahead = int(inputs.get("days_ahead") or 1)
    client = _build_calendar_client()
    return {"events": client.list_events(days_ahead=days_ahead)}
```

Create `apps/core/skills/search_email/manifest.yaml`:

```yaml
id: search_email
name: Search Email
description: Searches your Gmail inbox. Accepts Gmail query syntax, e.g. "from:someone newer_than:7d".
voice_invokable: true
input_schema:
  type: object
  properties:
    query:
      type: string
  required:
    - query
output_schema:
  type: object
  properties:
    messages:
      type: array
```

Create `apps/core/skills/search_email/skill.py`:

```python
from googleapiclient.discovery import build

from core.config import get_settings
from core.providers.google.auth import get_google_credentials
from core.providers.google.gmail import GmailClient


def _build_gmail_client() -> GmailClient:
    creds = get_google_credentials(get_settings())
    service = build("gmail", "v1", credentials=creds)
    return GmailClient(service)


def run(inputs: dict) -> dict:
    client = _build_gmail_client()
    return {"messages": client.search_messages(inputs["query"])}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_skills_read.py -v`
Expected: PASS (5 tests)

Then the full suite: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: 0 failures.

- [ ] **Step 5: Commit**

```bash
git add apps/core/skills/get_calendar_events/ apps/core/skills/search_email/ apps/core/tests/test_google_skills_read.py
git commit -m "feat(core): add get_calendar_events and search_email skills (voice-enabled, read-only)"
```

---

### Task 5: Write skills — `draft_email` + `create_calendar_event`

**Files:**
- Create: `apps/core/skills/draft_email/manifest.yaml`
- Create: `apps/core/skills/draft_email/skill.py`
- Create: `apps/core/skills/create_calendar_event/manifest.yaml`
- Create: `apps/core/skills/create_calendar_event/skill.py`
- Test: `apps/core/tests/test_google_skills_write.py`

**Interfaces:**
- Produces: `draft_email.run({"to", "subject", "body"}) -> {"draft_id", "to", "subject"}`; `create_calendar_event.run({"title", "start_iso", "end_iso", "description"?}) -> {"event_id", "html_link", "title", "start", "end"}`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_google_skills_write.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_skills_write.py -v`
Expected: FAIL — `loaded is None`

- [ ] **Step 3: Write minimal implementation**

Create `apps/core/skills/draft_email/manifest.yaml`:

```yaml
id: draft_email
name: Draft Email
description: Creates a DRAFT email in your Gmail account. Never sends — you review and send it yourself in Gmail.
voice_invokable: false
input_schema:
  type: object
  properties:
    to:
      type: string
    subject:
      type: string
    body:
      type: string
  required:
    - to
    - subject
    - body
output_schema:
  type: object
  properties:
    draft_id:
      type: string
    to:
      type: string
    subject:
      type: string
```

Create `apps/core/skills/draft_email/skill.py`:

```python
from googleapiclient.discovery import build

from core.config import get_settings
from core.providers.google.auth import get_google_credentials
from core.providers.google.gmail import GmailClient


def _build_gmail_client() -> GmailClient:
    creds = get_google_credentials(get_settings())
    service = build("gmail", "v1", credentials=creds)
    return GmailClient(service)


def run(inputs: dict) -> dict:
    client = _build_gmail_client()
    return client.create_draft(inputs["to"], inputs["subject"], inputs["body"])
```

Create `apps/core/skills/create_calendar_event/manifest.yaml`:

```yaml
id: create_calendar_event
name: Create Calendar Event
description: Creates an event on your primary Google Calendar. Times must be ISO 8601 with timezone offset.
voice_invokable: false
input_schema:
  type: object
  properties:
    title:
      type: string
    start_iso:
      type: string
    end_iso:
      type: string
    description:
      type: string
  required:
    - title
    - start_iso
    - end_iso
output_schema:
  type: object
  properties:
    event_id:
      type: string
    html_link:
      type: string
    title:
      type: string
    start:
      type: string
    end:
      type: string
```

Create `apps/core/skills/create_calendar_event/skill.py`:

```python
from googleapiclient.discovery import build

from core.config import get_settings
from core.providers.google.auth import get_google_credentials
from core.providers.google.calendar import GoogleCalendarClient


def _build_calendar_client() -> GoogleCalendarClient:
    creds = get_google_credentials(get_settings())
    service = build("calendar", "v3", credentials=creds)
    return GoogleCalendarClient(service)


def run(inputs: dict) -> dict:
    client = _build_calendar_client()
    return client.create_event(
        title=inputs["title"],
        start_iso=inputs["start_iso"],
        end_iso=inputs["end_iso"],
        description=inputs.get("description", ""),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_skills_write.py -v`
Expected: PASS (4 tests)

Then the full suite: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: 0 failures.

- [ ] **Step 5: Commit**

```bash
git add apps/core/skills/draft_email/ apps/core/skills/create_calendar_event/ apps/core/tests/test_google_skills_write.py
git commit -m "feat(core): add draft_email and create_calendar_event skills (UI-only writes)"
```

---

### Task 6: Live contract tests + full verification + manual smoke check

**Files:**
- Create: `apps/core/tests/test_google_contract.py`
- No other changes — the rest is verification.

**Interfaces:** None new.

- [ ] **Step 1: Write the contract tests** (these PASS on Stephen's machine where the token exists, SKIP elsewhere — mirrors `test_piper_contract.py`)

Create `apps/core/tests/test_google_contract.py`:

```python
from pathlib import Path

import pytest

from core.config import Settings
from core.providers.google.auth import BASE_DIR

TOKEN_PATH = BASE_DIR / Settings(anthropic_api_key=None).google_token_path


@pytest.mark.skipif(not TOKEN_PATH.exists(), reason="Google token not present")
def test_calendar_lists_real_events():
    from googleapiclient.discovery import build

    from core.providers.google.auth import get_google_credentials
    from core.providers.google.calendar import GoogleCalendarClient

    creds = get_google_credentials(Settings(anthropic_api_key=None))
    client = GoogleCalendarClient(build("calendar", "v3", credentials=creds))

    events = client.list_events(days_ahead=7)

    assert isinstance(events, list)
    for event in events:
        assert set(event.keys()) == {"title", "start", "end", "location", "attendee_count"}


@pytest.mark.skipif(not TOKEN_PATH.exists(), reason="Google token not present")
def test_gmail_searches_real_inbox():
    from googleapiclient.discovery import build

    from core.providers.google.auth import get_google_credentials
    from core.providers.google.gmail import GmailClient

    creds = get_google_credentials(Settings(anthropic_api_key=None))
    client = GmailClient(build("gmail", "v1", credentials=creds))

    messages = client.search_messages("in:inbox", limit=2)

    assert isinstance(messages, list)
    for message in messages:
        assert set(message.keys()) == {"from_", "subject", "date", "snippet"}
```

- [ ] **Step 2: Run the contract tests and the full suite**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_google_contract.py -v`
Expected: PASS (2 tests, real API calls)

Run: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all pass, 0 failed.

- [ ] **Step 3: Manual smoke check against a live backend**

Start the backend from `apps/core`: `.venv/bin/uvicorn core.app:create_app --factory --port 8420 &`, wait ~2s, then:

```bash
curl -s http://127.0.0.1:8420/skills | python3 -c "import sys, json; print([s['id'] for s in json.load(sys.stdin)])"
```
Expected: includes `get_calendar_events`, `search_email`, `draft_email`, `create_calendar_event`.

```bash
curl -s -X POST http://127.0.0.1:8420/skills/get_calendar_events/invoke -H "Content-Type: application/json" -d '{"inputs": {"days_ahead": 2}}'
```
Expected: real events from Stephen's calendar.

```bash
curl -s -X POST http://127.0.0.1:8420/skills/search_email/invoke -H "Content-Type: application/json" -d '{"inputs": {"query": "in:inbox newer_than:2d"}}'
```
Expected: real recent inbox messages.

```bash
curl -s -X POST http://127.0.0.1:8420/skills/draft_email/invoke -H "Content-Type: application/json" -d '{"inputs": {"to": "stephenlese96@gmail.com", "subject": "Jarvis draft test", "body": "This draft was created by Jarvis as a smoke test. Safe to delete."}}'
```
Expected: a `draft_id` — then verify it exists AND delete it via the API (cleanup):

```bash
# list drafts to confirm, then delete the test draft by id (use the draft_id from above)
curl -s -X POST http://127.0.0.1:8420/skills/create_calendar_event/invoke -H "Content-Type: application/json" -d '{"inputs": {"title": "Jarvis smoke test event (safe to delete)", "start_iso": "2026-07-08T23:30:00-04:00", "end_iso": "2026-07-08T23:45:00-04:00", "description": "Created by the M8b smoke test."}}'
```
Expected: an `event_id` + `html_link`. Then delete the test event and the test draft directly via a short Python snippet using the same credentials (the skills deliberately have no delete capability — cleanup goes through the raw API):

```python
# run with .venv/bin/python - <<'EOF' style; delete the smoke-test artifacts
from googleapiclient.discovery import build
from core.config import Settings
from core.providers.google.auth import get_google_credentials
creds = get_google_credentials(Settings(anthropic_api_key=None))
build("calendar", "v3", credentials=creds).events().delete(calendarId="primary", eventId="<event_id>").execute()
build("gmail", "v1", credentials=creds).users().drafts().delete(userId="me", id="<draft_id>").execute()
print("cleaned up")
EOF
```

Stop the backend afterward and confirm port 8420 is free.

- [ ] **Step 4: Commit the contract tests and update the progress ledger**

```bash
git add apps/core/tests/test_google_contract.py
git commit -m "test(core): add live Google API contract tests (skip without token)"
```

Append to `.superpowers/sdd/progress.md`:

```
Task 6: complete (contract tests green against real APIs; all four skills manually verified end-to-end against Stephen's real account via a live backend; test draft + test event created and cleaned up; full suite green)

## All tasks complete. Ready for final whole-branch review.
```
