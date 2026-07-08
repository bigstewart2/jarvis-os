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
