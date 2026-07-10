import json
from datetime import datetime

from googleapiclient.discovery import build

from core.config import get_settings
from core.providers.google.auth import get_google_credentials
from core.providers.google.calendar import GoogleCalendarClient
from core.providers.google.gmail import GmailClient
from core.providers.llm.factory import get_llm_provider

DEFAULT_EMAIL_QUERY = "newer_than:1d (is:unread OR is:important) -category:promotions -category:social"

BRIEF_SYSTEM_PROMPT = (
    "You are Jarvis, a personal assistant writing a short morning brief for your "
    "one user, Stephen. You receive today's date, his calendar events, and recent "
    "notable emails as JSON. Write a brief that reads well out loud AND on screen: "
    "2-4 short paragraphs, plain prose, no markdown syntax, no bullet characters. "
    "Open with a one-line orientation (day, how busy it looks). Then cover the "
    "calendar in time order with times in plain 12-hour form. Then the emails that "
    "actually matter — group or skip noise, never enumerate all of them. Close with "
    "one practical suggestion for the day if the data supports one, otherwise don't. "
    "If a section is empty, say so in a few words rather than apologizing."
)


def _build_calendar_client() -> GoogleCalendarClient:
    creds = get_google_credentials(get_settings())
    service = build("calendar", "v3", credentials=creds)
    return GoogleCalendarClient(service)


def _build_gmail_client() -> GmailClient:
    creds = get_google_credentials(get_settings())
    service = build("gmail", "v1", credentials=creds)
    return GmailClient(service)


def run(inputs: dict) -> dict:
    days_ahead = int(inputs.get("days_ahead") or 1)
    email_query = inputs.get("email_query") or DEFAULT_EMAIL_QUERY

    events: list[dict] = []
    messages: list[dict] = []
    source_errors: list[str] = []

    try:
        events = _build_calendar_client().list_events(days_ahead=days_ahead)
    except Exception as exc:
        source_errors.append(f"calendar unavailable: {exc}")

    try:
        messages = _build_gmail_client().search_messages(email_query)
    except Exception as exc:
        source_errors.append(f"email unavailable: {exc}")

    now = datetime.now().astimezone()
    payload = {
        "now": now.strftime("%A, %B %-d, %Y, %-I:%M %p"),
        "calendar_events": events,
        "recent_emails": messages,
        "source_errors": source_errors,
    }

    provider = get_llm_provider(get_settings())
    brief = provider.complete(json.dumps(payload), system=BRIEF_SYSTEM_PROMPT)

    return {"brief": brief.strip(), "events": events, "messages": messages}
