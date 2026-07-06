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


def test_llm_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.llm_provider == "anthropic"
    assert settings.anthropic_model == "claude-sonnet-4-5"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2:3b"


def test_anthropic_api_key_resolves_from_bare_env_var(monkeypatch):
    monkeypatch.delenv("JARVIS_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bare-env-key")
    settings = Settings()
    assert settings.anthropic_api_key == "bare-env-key"


def test_anthropic_api_key_prefers_jarvis_prefixed_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bare-env-key")
    monkeypatch.setenv("JARVIS_ANTHROPIC_API_KEY", "prefixed-env-key")
    settings = Settings()
    assert settings.anthropic_api_key == "prefixed-env-key"
