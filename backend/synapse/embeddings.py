from __future__ import annotations

import hashlib
import json

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from synapse.config import Settings
from synapse.ingestion import NormalizedChunk, normalize_file


async def embed_chunks(settings: Settings, chunks: list[NormalizedChunk]) -> list[list[float]]:
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=120) as client:
        response = await client.post("/api/embed", json={
            "model": settings.embedding_model,
            "input": [chunk.content for chunk in chunks],
        })
        response.raise_for_status()
        return response.json()["embeddings"]


async def ingest_file(
    engine: AsyncEngine, settings: Settings, filename: str, content: bytes
) -> dict:
    chunks = [chunk for chunk in normalize_file(filename, content) if chunk.content.strip()]
    embeddings = await embed_chunks(settings, chunks)
    source_id = hashlib.md5(f"{filename}:{len(content)}".encode()).hexdigest()
    revision_id = hashlib.sha256(content).hexdigest()[:32]

    async with engine.begin() as connection:
        await connection.execute(text("""
            INSERT INTO sources (id, name, source_type, uri)
            VALUES (CAST(:id AS uuid), :name, 'file', :uri)
            ON CONFLICT (id) DO NOTHING
        """), {"id": source_id, "name": filename, "uri": filename})
        await connection.execute(text("""
            INSERT INTO document_revisions (id, source_id, content_hash, mime_type, revision_number)
            VALUES (CAST(:id AS uuid), CAST(:source_id AS uuid), :hash, :mime, 1)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": revision_id,
            "source_id": source_id,
            "hash": revision_id,
            "mime": "application/octet-stream",
        })
        for ordinal, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True), start=1):
            await connection.execute(text("""
                INSERT INTO chunks (revision_id, ordinal, content, locator, embedding)
                VALUES (CAST(:revision_id AS uuid), :ordinal, :content,
                        CAST(:locator AS jsonb), CAST(:embedding AS vector))
                ON CONFLICT (revision_id, ordinal) DO NOTHING
            """), {
                "revision_id": revision_id,
                "ordinal": ordinal,
                "content": chunk.content,
                "locator": json.dumps(chunk.locator),
                "embedding": "[" + ",".join(map(str, embedding)) + "]",
            })
    return {
        "source_id": source_id,
        "revision_id": revision_id,
        "filename": filename,
        "chunks": len(chunks),
    }
