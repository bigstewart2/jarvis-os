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


def test_voice_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.stt_provider == "faster_whisper"
    assert settings.stt_model == "small"
    assert settings.stt_compute_type == "int8"
    assert settings.tts_provider == "piper"
    assert settings.piper_voice == "en_US-lessac-medium"
    assert settings.voice_dir == "data/voice"


def test_claude_code_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.claude_code_binary == "claude"
    assert settings.claude_code_subpath == ""
    assert settings.claude_code_timeout_seconds == 600
    assert settings.claude_code_allowed_tools == (
        "Read,Glob,Grep,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
    )
    assert settings.claude_code_max_turns == 50


def test_automations_dir_default():
    settings = Settings(anthropic_api_key=None)
    assert settings.automations_dir == "automations"
