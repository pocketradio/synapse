from __future__ import annotations

import json
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from synapse.config import Settings

VerificationStatus = Literal["supported", "partial", "unsupported", "conflicting"]


class Claim(BaseModel):
    claim_text: str
    evidence_ids: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    claim_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    reason: str = ""


class JsonModelClient(Protocol):
    async def complete(self, prompt: str) -> dict: ...


class OllamaJsonClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, prompt: str) -> dict:
        async with httpx.AsyncClient(
            base_url=self.settings.ollama_base_url, timeout=120
        ) as client:
            response = await client.post("/api/chat", json={
                "model": self.settings.chat_model,
                "stream": False,
                "format": "json",
                "messages": [{"role": "user", "content": prompt}],
            })
            response.raise_for_status()
            return json.loads(response.json()["message"]["content"])


class ClaimGenerator:
    def __init__(self, client: JsonModelClient):
        self.client = client

    async def generate(self, question: str, evidence: list[dict]) -> list[Claim]:
        if not evidence:
            return []
        prompt = (
            "Create only material claims supported by the evidence. "
            "Return JSON with a claims array. Each claim must contain claim_text "
            "and evidence_ids. Do not add facts not present in evidence.\n"
            f"Question: {question}\nEvidence: {json.dumps(evidence)}"
        )
        try:
            payload = await self.client.complete(prompt)
            return [Claim.model_validate(item) for item in payload.get("claims", [])]
        except Exception:
            return []


class ClaimVerifier:
    def __init__(self, client: JsonModelClient):
        self.client = client

    async def verify(self, claims: list[Claim], evidence: list[dict]) -> list[VerificationResult]:
        if not claims:
            return []
        prompt = (
            "Verify each claim only against the supplied evidence. "
            "Return JSON with a results array. "
            "Status must be supported, partial, unsupported, or conflicting. "
            "Keep only evidence_ids that actually exist.\n"
            f"Claims: {json.dumps([claim.model_dump() for claim in claims])}\n"
            f"Evidence: {json.dumps(evidence)}"
        )
        try:
            payload = await self.client.complete(prompt)
            return [VerificationResult.model_validate(item) for item in payload.get("results", [])]
        except Exception:
            return [
                VerificationResult(
                    claim_text=claim.claim_text,
                    evidence_ids=[],
                    status="unsupported",
                    reason="verification unavailable",
                )
                for claim in claims
            ]


def validate_citations(
    results: list[VerificationResult], evidence: list[dict]
) -> list[VerificationResult]:
    valid_ids = {item["evidence_id"] for item in evidence}
    checked: list[VerificationResult] = []
    for result in results:
        citations = [evidence_id for evidence_id in result.evidence_ids if evidence_id in valid_ids]
        status = result.status if citations or result.status == "unsupported" else "unsupported"
        checked.append(result.model_copy(update={"evidence_ids": citations, "status": status}))
    return checked


def render_answer(results: list[VerificationResult]) -> str:
    usable = [result for result in results if result.status != "unsupported"]
    if not usable:
        return "I cannot answer this from the available evidence."
    return " ".join(
        f"{result.claim_text} "
        f"[{', '.join(result.evidence_ids)}]"
        + (f" ({result.status})" if result.status != "supported" else "")
        for result in usable
    )
