import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
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


@app.get("/api/knowledge/summary")
async def knowledge_summary() -> dict:
    """Return the small Step 2 corpus summary for the reviewer screen and tests."""
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("""
                SELECT
                    (SELECT count(*) FROM sources) AS sources,
                    (SELECT count(*) FROM chunks) AS chunks,
                    (SELECT count(*) FROM entities) AS entities,
                    (SELECT count(*) FROM relationships) AS relationships
            """))
            row = result.mappings().one()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Knowledge schema is unavailable") from exc
    return {key: int(value) for key, value in row.items()}


@app.get("/api/knowledge/chunks/{chunk_id}")
async def get_chunk_provenance(chunk_id: str) -> dict:
    """Show a chunk and the exact source locator that produced it."""
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("""
                SELECT
                    c.id AS chunk_id,
                    c.content,
                    c.locator,
                    s.id AS source_id,
                    s.name AS source_name,
                    s.uri,
                    r.mime_type,
                    r.revision_number
                FROM chunks c
                JOIN document_revisions r ON r.id = c.revision_id
                JOIN sources s ON s.id = r.source_id
                WHERE c.id = :chunk_id
            """), {"chunk_id": chunk_id})
            row = result.mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Knowledge schema is unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return dict(row)
