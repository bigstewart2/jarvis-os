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

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_SCOPES)
    except ValueError as exc:
        raise GoogleAuthError(_REAUTH_HINT) from exc

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            raise GoogleAuthError(_REAUTH_HINT)

    return creds
