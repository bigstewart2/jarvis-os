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
