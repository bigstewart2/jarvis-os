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
