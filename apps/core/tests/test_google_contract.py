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
