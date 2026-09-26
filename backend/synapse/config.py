from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Synapse"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://synapse:synapse@localhost:5432/synapse"
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3.5:9b"
    embedding_model: str = "qwen3-embedding:0.6b"
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
