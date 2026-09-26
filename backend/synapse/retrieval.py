from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from synapse.cache import RetrievalCache
from synapse.config import Settings
from synapse.embeddings import embed_texts


@dataclass
class EvidenceCandidate:
    candidate_id: str
    kind: str
    content: str
    source_id: str
    source_name: str
    locator: dict
    rank: int | None = None
    score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "content": self.content,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "locator": self.locator,
            "rank": self.rank,
            "score": self.score,
        }


async def lexical_search(engine: AsyncEngine, question: str) -> list[EvidenceCandidate]:
    identifier = next(
        iter(re.findall(r"\b[a-z]+[A-Z][A-Za-z]*\b|\b\w+\(\)", question)), ""
    )
    query = text("""
        SELECT c.id::text AS candidate_id, 'chunk' AS kind, c.content,
               s.id::text AS source_id, s.name AS source_name, c.locator,
               ts_rank_cd(c.search_vector, plainto_tsquery('english', :question)) AS score
        FROM chunks c
        JOIN document_revisions r ON r.id = c.revision_id
        JOIN sources s ON s.id = r.source_id
        WHERE c.search_vector @@ plainto_tsquery('english', :question)
           OR lower(c.content) LIKE '%' || lower(:question) || '%'
           OR (:identifier <> '' AND lower(c.content) LIKE '%' || lower(:identifier) || '%')
        ORDER BY score DESC, c.id
        LIMIT 20
    """)
    async with engine.connect() as connection:
        rows = (await connection.execute(query, {
            "question": question,
            "identifier": identifier,
        })).mappings().all()
    return [EvidenceCandidate(**dict(row), rank=index) for index, row in enumerate(rows, 1)]


async def vector_search(
    engine: AsyncEngine,
    settings: Settings,
    question: str,
    embedding: list[float] | None = None,
) -> list[EvidenceCandidate]:
    if embedding is None:
        embedding = (await embed_texts(settings, [question]))[0]
    query = text("""
        SELECT c.id::text AS candidate_id, 'chunk' AS kind, c.content,
               s.id::text AS source_id, s.name AS source_name, c.locator,
               (1 - (c.embedding <=> CAST(:embedding AS vector))) AS score
        FROM chunks c
        JOIN document_revisions r ON r.id = c.revision_id
        JOIN sources s ON s.id = r.source_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT 20
    """)
    async with engine.connect() as connection:
        rows = (await connection.execute(query, {
            "embedding": "[" + ",".join(map(str, embedding)) + "]",
        })).mappings().all()
    return [EvidenceCandidate(**dict(row), rank=index) for index, row in enumerate(rows, 1)]


async def graph_search(engine: AsyncEngine, question: str) -> list[EvidenceCandidate]:
    names = [part.lower() for part in question.replace("?", " ").split()]
    query = text("""
        WITH RECURSIVE walk(entity_id, depth) AS (
            SELECT id, 0 FROM entities WHERE lower(name) = ANY(CAST(:names AS text[]))
            UNION
            SELECT CASE
                       WHEN rel.subject_id = walk.entity_id THEN rel.object_id
                       ELSE rel.subject_id
                   END,
                   walk.depth + 1
            FROM walk
            JOIN relationships rel
              ON rel.subject_id = walk.entity_id OR rel.object_id = walk.entity_id
            WHERE walk.depth < 2
        )
        SELECT DISTINCT ON (rel.id)
               ('relationship:' || rel.id::text) AS candidate_id,
               'relationship' AS kind,
               c.content,
               s.id::text AS source_id,
               s.name AS source_name,
               c.locator,
               rel.confidence AS score
        FROM walk
        JOIN relationships rel ON rel.subject_id = walk.entity_id OR rel.object_id = walk.entity_id
        JOIN chunks c ON c.id = rel.evidence_chunk_id
        JOIN document_revisions r ON r.id = c.revision_id
        JOIN sources s ON s.id = r.source_id
        ORDER BY rel.id, walk.depth
        LIMIT 20
    """)
    async with engine.connect() as connection:
        rows = (await connection.execute(query, {"names": names})).mappings().all()
    return [EvidenceCandidate(**dict(row), rank=index) for index, row in enumerate(rows, 1)]


def reciprocal_rank_fusion(
    *result_sets: list[EvidenceCandidate], limit: int = 12
) -> list[EvidenceCandidate]:
    fused: dict[str, EvidenceCandidate] = {}
    rrf_scores: defaultdict[str, float] = defaultdict(float)
    for result_set in result_sets:
        for rank, candidate in enumerate(result_set, 1):
            fused.setdefault(candidate.candidate_id, candidate)
            rrf_scores[candidate.candidate_id] += 1 / (60 + rank)
    ordered = sorted(fused.values(), key=lambda item: rrf_scores[item.candidate_id], reverse=True)
    selected: list[EvidenceCandidate] = []
    source_counts: defaultdict[str, int] = defaultdict(int)
    for candidate in ordered:
        if source_counts[candidate.source_id] >= 3 and len(selected) < limit:
            continue
        candidate.score = rrf_scores[candidate.candidate_id]
        selected.append(candidate)
        source_counts[candidate.source_id] += 1
        if len(selected) == limit:
            break
    return selected


async def retrieve(
    engine: AsyncEngine,
    settings: Settings,
    question: str,
    strategy: str = "hybrid_graph",
    selected_tools: list[str] | None = None,
    cache: RetrievalCache | None = None,
) -> dict:
    tools = selected_tools or {
        "lexical": strategy in {"lexical", "hybrid", "hybrid_graph"},
        "vector": strategy in {"vector", "hybrid", "hybrid_graph"},
        "graph": strategy == "hybrid_graph",
    }
    cache_strategy = ",".join(sorted(tools)) if isinstance(tools, list) else strategy
    version = await cache.corpus_version(engine) if cache else "no-cache"
    if cache:
        exact = await cache.get_exact_retrieval(version, cache_strategy, question)
        if exact:
            return {**exact, "cache_level": "exact"}

    uses_lexical = "lexical" in tools if isinstance(tools, list) else tools["lexical"]
    uses_vector = "vector" in tools if isinstance(tools, list) else tools["vector"]
    uses_graph = "graph" in tools if isinstance(tools, list) else tools["graph"]
    embedding = None
    if uses_vector:
        embedding = await cache.get_embedding(version, question) if cache else None
        if embedding is None:
            embedding = (await embed_texts(settings, [question]))[0]
            if cache:
                await cache.set_embedding(version, question, embedding)
        if cache:
            semantic = await cache.get_semantic_retrieval(version, cache_strategy, embedding)
            if semantic:
                return {**semantic, "cache_level": "semantic"}

    tasks = []
    if uses_lexical:
        tasks.append(lexical_search(engine, question))
    if uses_vector:
        tasks.append(vector_search(engine, settings, question, embedding))
    if uses_graph:
        tasks.append(graph_search(engine, question))
    result_sets = await asyncio.gather(*tasks)
    index = 0
    lexical = result_sets[index] if uses_lexical else []
    index += int(uses_lexical)
    vector = result_sets[index] if uses_vector else []
    index += int(uses_vector)
    graph = result_sets[index] if uses_graph else []
    if len([item for item in (uses_lexical, uses_vector, uses_graph) if item]) == 1:
        candidates = (lexical or vector or graph)[:12]
    else:
        candidates = reciprocal_rank_fusion(lexical, vector, graph)
    result = {
        "strategy": strategy,
        "engine_counts": {"lexical": len(lexical), "vector": len(vector), "graph": len(graph)},
        "candidates": [candidate.as_dict() for candidate in candidates],
        "cache_level": "none",
    }
    if cache:
        await cache.set_exact_retrieval(version, cache_strategy, question, result)
        if embedding:
            await cache.set_semantic_retrieval(version, cache_strategy, embedding, result)
    return result
