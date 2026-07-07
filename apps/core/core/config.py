from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_", populate_by_name=True)

    database_url: str = "sqlite:///./jarvis.db"
    skills_dir: str = "skills"
    host: str = "127.0.0.1"
    port: int = 8420

    llm_provider: Literal["anthropic", "ollama"] = "anthropic"
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JARVIS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_model: str = "claude-sonnet-4-5"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    stt_provider: Literal["faster_whisper"] = "faster_whisper"
    stt_model: str = "small"
    stt_compute_type: str = "int8"
    tts_provider: Literal["piper"] = "piper"
    piper_voice: str = "en_US-lessac-medium"
    piper_voices_dir: str = "voices"
    voice_dir: str = "data/voice"

    claude_code_binary: str = "claude"
    claude_code_subpath: str = ""
    claude_code_timeout_seconds: int = 600
    claude_code_allowed_tools: str = (
        "Read,Glob,Grep,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
    )
    claude_code_max_turns: int = 50

    automations_dir: str = "automations"
    knowledge_vault_dir: str = "tests/fixtures/vault"


def get_settings() -> Settings:
    return Settings()
