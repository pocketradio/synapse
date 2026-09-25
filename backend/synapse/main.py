import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from synapse.config import get_settings
from synapse.health import check_database, check_ollama, overall_status

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

app = FastAPI(
    title="Synapse API",
    description="System boundary and dependency health API",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    database, ollama = await asyncio.gather(
        check_database(engine),
        check_ollama(settings),
    )
    return {
        "status": overall_status(database, ollama),
        "application": {
            "name": settings.app_name,
            "environment": settings.environment,
            "api": "healthy",
        },
        "services": {
            "database": database,
            "ollama": ollama,
        },
    }

