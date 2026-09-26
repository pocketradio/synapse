from __future__ import annotations

import hashlib
import json
import struct

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from synapse.config import Settings


class RetrievalCache:
    index_name = "synapse:semantic_index"
    semantic_prefix = "synapse:semantic:"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis: Redis = Redis.from_url(settings.redis_url, decode_responses=False)

    @staticmethod
    def normalize(question: str) -> str:
        return " ".join(question.casefold().split())

    async def corpus_version(self, engine: AsyncEngine) -> str:
        query = text("""
            SELECT COALESCE(
                md5(string_agg(content_hash, ',' ORDER BY content_hash)),
                'empty'
            ) AS version
            FROM document_revisions
        """)
        async with engine.connect() as connection:
            return str((await connection.execute(query)).scalar_one())

    def _question_hash(self, question: str) -> str:
        return hashlib.sha256(self.normalize(question).encode()).hexdigest()

    def _base(self, version: str, strategy: str, question: str) -> str:
        return f"synapse:{version}:{strategy}:{self._question_hash(question)}"

    async def get_exact_retrieval(self, version: str, strategy: str, question: str) -> dict | None:
        try:
            value = await self.redis.get(f"{self._base(version, strategy, question)}:result")
            return json.loads(value) if value else None
        except Exception:
            return None

    async def set_exact_retrieval(
        self, version: str, strategy: str, question: str, result: dict
    ) -> None:
        try:
            await self.redis.setex(
                f"{self._base(version, strategy, question)}:result",
                self.settings.cache_ttl_seconds,
                json.dumps(result),
            )
        except Exception:
            return

    async def get_embedding(self, version: str, question: str) -> list[float] | None:
        try:
            value = await self.redis.get(
                f"synapse:embedding:{version}:{self.settings.embedding_model}:{self._question_hash(question)}"
            )
            return json.loads(value) if value else None
        except Exception:
            return None

    async def set_embedding(self, version: str, question: str, embedding: list[float]) -> None:
        try:
            await self.redis.setex(
                f"synapse:embedding:{version}:{self.settings.embedding_model}:{self._question_hash(question)}",
                self.settings.cache_ttl_seconds,
                json.dumps(embedding),
            )
        except Exception:
            return

    async def ensure_semantic_index(self, dimension: int) -> None:
        try:
            await self.redis.execute_command("FT.INFO", self.index_name)
        except Exception:
            try:
                await self.redis.execute_command(
                    "FT.CREATE", self.index_name, "ON", "HASH", "PREFIX", "1",
                    self.semantic_prefix, "SCHEMA", "embedding", "VECTOR", "HNSW", "6",
                    "TYPE", "FLOAT32", "DIM", str(dimension), "DISTANCE_METRIC", "COSINE",
                    "version", "TAG", "strategy", "TAG",
                )
            except Exception:
                return

    async def get_semantic_retrieval(
        self, version: str, strategy: str, embedding: list[float]
    ) -> dict | None:
        try:
            await self.ensure_semantic_index(len(embedding))
            vector = struct.pack(f"{len(embedding)}f", *embedding)
            query = (
                f"(@version:{{{version}}} @strategy:{{{strategy}}})=>"
                "[KNN 1 @embedding $vector AS distance]"
            )
            raw = await self.redis.execute_command(
                "FT.SEARCH", self.index_name, query, "PARAMS", "2", "vector", vector,
                "SORTBY", "distance", "DIALECT", "2",
            )
            if not raw or raw[0] == 0:
                return None
            field_values = raw[2] if len(raw) > 2 else []
            fields = dict(zip(field_values[::2], field_values[1::2], strict=False))
            distance = float(fields.get(b"distance", b"1"))
            if 1 - distance < self.settings.semantic_cache_threshold:
                return None
            return json.loads(fields[b"result"])
        except Exception:
            return None

    async def set_semantic_retrieval(
        self, version: str, strategy: str, embedding: list[float], result: dict
    ) -> None:
        try:
            await self.ensure_semantic_index(len(embedding))
            key = (
                f"{self.semantic_prefix}"
                f"{hashlib.sha256(json.dumps(embedding).encode()).hexdigest()}"
            )
            vector = struct.pack(f"{len(embedding)}f", *embedding)
            await self.redis.hset(key, mapping={
                "version": version,
                "strategy": strategy,
                "embedding": vector,
                "result": json.dumps(result),
            })
            await self.redis.expire(key, self.settings.cache_ttl_seconds)
        except Exception:
            return
