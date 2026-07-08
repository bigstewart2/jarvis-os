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
