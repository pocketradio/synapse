from __future__ import annotations

import json
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from synapse.config import Settings

VerificationStatus = Literal["supported", "partial", "unsupported", "conflicting"]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_text: str
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    reason: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)


class ClaimsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[Claim] = Field(default_factory=list, max_length=8)


class VerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[VerificationResult] = Field(default_factory=list, max_length=8)


class GroundedAnswerPayload(VerificationPayload):
    """One-call answer contract: claims, citations, and support status together."""


def parse_claims(payload: dict) -> list[Claim]:
    try:
        return ClaimsPayload.model_validate(payload).claims
    except ValidationError:
        return [Claim.model_validate(payload)]


def parse_verification(payload: dict) -> list[VerificationResult]:
    try:
        return VerificationPayload.model_validate(payload).results
    except ValidationError:
        return [VerificationResult.model_validate(payload)]


def parse_grounded_answer(payload: dict) -> list[VerificationResult]:
    return GroundedAnswerPayload.model_validate(payload).results


class ModelResponseError(RuntimeError):
    """Raised when a model provider returns an unusable response."""


class JsonModelClient(Protocol):
    async def complete(self, prompt: str) -> dict: ...


class OllamaJsonClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, prompt: str) -> dict:
        async with httpx.AsyncClient(
            base_url=self.settings.ollama_base_url, timeout=30
        ) as client:
            response = await client.post("/api/chat", json={
                "model": self.settings.chat_model,
                "stream": False,
                "format": "json",
                "think": False,
                "messages": [{"role": "user", "content": prompt}],
            })
            response.raise_for_status()
            return json.loads(response.json()["message"]["content"])


class OpenRouterJsonClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, prompt: str) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.openrouter_api_key}"}
        async with httpx.AsyncClient(
            base_url=self.settings.openrouter_base_url, headers=headers, timeout=45
        ) as client:
            response = await client.post("/chat/completions", json={
                "model": self.settings.openrouter_model,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            })
            try:
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                payload = json.loads(content)
            except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                detail = response.text[:300].replace("\n", " ")
                raise ModelResponseError(
                    f"openrouter returned an unusable response ({response.status_code}): {detail}"
                ) from exc
            if not isinstance(payload, dict):
                raise ModelResponseError("openrouter returned JSON that was not an object")
            return payload


def create_json_model_client(settings: Settings) -> JsonModelClient:
    if settings.chat_provider == "openrouter":
        return OpenRouterJsonClient(settings)
    return OllamaJsonClient(settings)


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
        payload = await self.client.complete(prompt)
        return parse_claims(payload)

    async def generate_grounded(
        self, question: str, evidence: list[dict]
    ) -> list[VerificationResult]:
        if not evidence:
            return []
        prompt = (
            "Answer using only the supplied evidence. Return JSON with a results array. "
            "Each result must contain claim_text, evidence_ids, status, reason, and optional "
            "confidence. Status must be supported, partial, unsupported, or conflicting. "
            "Every material claim must cite evidence_ids. Do not add facts "
            "not present in evidence.\n"
            f"Question: {question}\nEvidence: {json.dumps(evidence)}"
        )
        return parse_grounded_answer(await self.client.complete(prompt))


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
        payload = await self.client.complete(prompt)
        return parse_verification(payload)


def validate_claims(claims: list[Claim], evidence: list[dict]) -> list[Claim]:
    valid_ids = {item["evidence_id"] for item in evidence}
    checked: list[Claim] = []
    for claim in claims:
        citations = list(dict.fromkeys(
            evidence_id for evidence_id in claim.evidence_ids if evidence_id in valid_ids
        ))
        if citations:
            checked.append(claim.model_copy(update={"evidence_ids": citations}))
    return checked


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
