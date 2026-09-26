import pytest

from synapse.config import Settings
from synapse.embeddings import embed_chunks
from synapse.ingestion import NormalizedChunk


class FakeResponse:
    def __init__(self, count: int):
        self.count = count

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        return {"embeddings": [[float(index)] for index in range(self.count)]}


class FakeClient:
    calls: list[list[str]] = []

    def __init__(self, **_: object):
        return

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return

    async def post(self, _: str, json: dict) -> FakeResponse:
        self.calls.append(json["input"])
        return FakeResponse(len(json["input"]))


@pytest.mark.asyncio
async def test_embedding_batches_preserve_chunk_count(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.calls = []
    monkeypatch.setattr("synapse.embeddings.httpx.AsyncClient", FakeClient)
    settings = Settings(embedding_batch_size=2)
    chunks = [NormalizedChunk(f"chunk {index}", {"line": index}) for index in range(5)]
    embeddings = await embed_chunks(settings, chunks)
    assert [len(call) for call in FakeClient.calls] == [2, 2, 1]
    assert len(embeddings) == len(chunks)
