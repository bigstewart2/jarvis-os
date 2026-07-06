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


def get_settings() -> Settings:
    return Settings()
