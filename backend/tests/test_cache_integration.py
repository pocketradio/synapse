import pytest

from synapse.cache import RetrievalCache
from synapse.config import get_settings


@pytest.mark.asyncio
async def test_redis_semantic_cache_round_trip() -> None:
    cache = RetrievalCache(get_settings())
    embedding = [0.1, 0.2, 0.3, 0.4]
    result = {"strategy": "test", "candidates": []}
    await cache.set_semantic_retrieval("integrationtest", "test", embedding, result)
    assert await cache.get_semantic_retrieval("integrationtest", "test", embedding) == result
    await cache.redis.aclose()
