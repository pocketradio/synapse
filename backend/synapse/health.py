from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from synapse.config import Settings


async def check_database(engine: AsyncEngine) -> dict[str, Any]:
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        return {
            "status": "healthy" if version else "degraded",
            "pgvector": version or "missing",
            "detail": None if version else "PostgreSQL is reachable but pgvector is not installed.",
        }
    except Exception as exc:
        return {"status": "unhealthy", "pgvector": "unknown", "detail": str(exc)}


async def check_ollama(settings: Settings) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
        installed = [item["name"] for item in response.json().get("models", [])]
        chat_ready = any(name.startswith(settings.chat_model) for name in installed)
        embedding_ready = any(name.startswith(settings.embedding_model) for name in installed)
        return {
            "status": "healthy" if chat_ready and embedding_ready else "degraded",
            "chat_model": {"name": settings.chat_model, "available": chat_ready},
            "embedding_model": {
                "name": settings.embedding_model,
                "available": embedding_ready,
            },
            "installed_models": installed,
            "detail": None
            if chat_ready and embedding_ready
            else "Ollama is running, but one or more required models are missing.",
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "chat_model": {"name": settings.chat_model, "available": False},
            "embedding_model": {"name": settings.embedding_model, "available": False},
            "installed_models": [],
            "detail": str(exc),
        }


def overall_status(database: dict[str, Any], ollama: dict[str, Any]) -> str:
    states = {database["status"], ollama["status"]}
    if states == {"healthy"}:
        return "healthy"
    if "healthy" in states or "degraded" in states:
        return "degraded"
    return "unhealthy"

