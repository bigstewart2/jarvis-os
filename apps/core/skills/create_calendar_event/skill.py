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
