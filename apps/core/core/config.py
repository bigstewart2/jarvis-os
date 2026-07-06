from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    database_url: str = "sqlite:///./jarvis.db"
    skills_dir: str = "skills"
    host: str = "127.0.0.1"
    port: int = 8420


def get_settings() -> Settings:
    return Settings()
