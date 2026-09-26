from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Synapse"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://synapse:synapse@localhost:5432/synapse"
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3.5:9b"
    chat_provider: str = "ollama"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    embedding_model: str = "qwen3-embedding:0.6b"
    cors_origins: str = "http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 86400
    semantic_cache_threshold: float = 0.95
    embedding_batch_size: int = 32

    @property
    def active_chat_model(self) -> str:
        return self.openrouter_model if self.chat_provider == "openrouter" else self.chat_model

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
