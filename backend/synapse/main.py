import asyncio

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from synapse.cache import RetrievalCache
from synapse.config import get_settings
from synapse.embeddings import ingest_file
from synapse.health import check_database, check_ollama, overall_status
from synapse.retrieval import retrieve
from synapse.workflow import BoundedQueryWorkflow

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
query_workflow = BoundedQueryWorkflow(engine, settings)
retrieval_cache = RetrievalCache(settings)

app = FastAPI(
    title="Synapse API",
    description="System boundary and dependency health API",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RetrievalRequest(BaseModel):
    question: str
    strategy: str = "hybrid_graph"


class QueryRequest(BaseModel):
    question: str


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


@app.post("/api/sources/files")
async def ingest_files(files: list[UploadFile] = File(...)) -> dict:  # noqa: B008
    results = []
    for file in files:
        content = await file.read()
        try:
            results.append(await ingest_file(engine, settings, file.filename or "upload", content))
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Could not ingest {file.filename}"
            ) from exc
    return {"files": results}


@app.post("/api/retrieval/search")
async def retrieval_search(request: RetrievalRequest) -> dict:
    if request.strategy not in {"lexical", "vector", "hybrid", "hybrid_graph"}:
        raise HTTPException(status_code=400, detail="Unsupported retrieval strategy")
    try:
        return await retrieve(
            engine, settings, request.question, request.strategy, cache=retrieval_cache
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Retrieval is unavailable") from exc


@app.post("/api/query")
async def query(request: QueryRequest) -> dict:
    try:
        return await query_workflow.run(request.question)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Query workflow is unavailable") from exc


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
