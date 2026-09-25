from synapse.config import Settings


def test_defaults_describe_local_stack() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.chat_model == "qwen3.5:9b"
    assert settings.embedding_model == "qwen3-embedding:0.6b"


def test_cors_origins_are_parsed() -> None:
    settings = Settings(_env_file=None, cors_origins="http://localhost:3000, http://localhost:3001")

    assert settings.cors_origin_list == ["http://localhost:3000", "http://localhost:3001"]

