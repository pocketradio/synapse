from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from synapse.workflow_types import ToolName

RouteKind = Literal["exact", "semantic", "relationship", "hybrid"]


class RouteDecision(BaseModel):
    kind: RouteKind
    tools: list[ToolName]
    generate_answer: bool
    verify_answer: bool
    reason: str


_IDENTIFIER = re.compile(
    r"(?:\b[a-z_][A-Za-z0-9_]*\(\)|\b[A-Z][A-Za-z0-9]*(?:Service|Queue)\b|"
    r"\b[A-Z][a-z]+[A-Z]\w*\b)"
)
_RELATIONSHIP = re.compile(r"\b(depends?|uses?|calls?|connects?|relationship|path|between)\b", re.I)
_EXPLANATION = re.compile(r"\b(how|why|explain|recover|summarize|difference)\b", re.I)
_KNOWN_ENTITY_HINT = re.compile(r"\b(redis|postgres(?:ql)?|checkout|payment|queue|service)\b", re.I)


def route_question(question: str) -> RouteDecision:
    identifier = bool(_IDENTIFIER.search(question))
    relationship = bool(_RELATIONSHIP.search(question))
    explanation = bool(_EXPLANATION.search(question))
    entity_hint = bool(_KNOWN_ENTITY_HINT.search(question)) or identifier

    if identifier and not relationship and not explanation:
        return RouteDecision(
            kind="exact",
            tools=["lexical"],
            generate_answer=False,
            verify_answer=False,
            reason="identifier lookup",
        )
    if relationship and entity_hint and explanation:
        return RouteDecision(
            kind="relationship",
            tools=["lexical", "vector", "graph"],
            generate_answer=True,
            verify_answer=True,
            reason="relationship and explanatory intent",
        )
    if relationship and entity_hint:
        return RouteDecision(
            kind="relationship",
            tools=["lexical", "graph"],
            generate_answer=True,
            verify_answer=True,
            reason="relationship intent with known entity hint",
        )
    if explanation:
        return RouteDecision(
            kind="semantic",
            tools=["vector"],
            generate_answer=True,
            verify_answer=True,
            reason="explanatory intent",
        )
    return RouteDecision(
        kind="hybrid",
        tools=["lexical", "vector", "graph"],
        generate_answer=True,
        verify_answer=True,
        reason="uncertain intent uses hybrid fallback",
    )
