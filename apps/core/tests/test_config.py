from core.config import Settings, get_settings


def test_default_settings():
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.database_url == "sqlite:///./jarvis.db"
    assert settings.port == 8420


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_PORT", "9999")
    settings = get_settings()
    assert settings.port == 9999
