from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from synapse.config import Settings
from synapse.retrieval import (
    EvidenceCandidate,
    graph_search,
    lexical_search,
    reciprocal_rank_fusion,
    vector_search,
)

ToolName = Literal["lexical", "vector", "graph"]
Tool = Callable[[str], Awaitable[list[EvidenceCandidate]]]


class QueryPlan(BaseModel):
    tools: list[ToolName] = Field(min_length=1, max_length=3)


class Planner(Protocol):
    async def plan(self, question: str) -> QueryPlan: ...


class OllamaPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def plan(self, question: str) -> QueryPlan:
        prompt = (
            "Choose retrieval tools for this question. Return JSON only with a tools array. "
            "Allowed tools: lexical, vector, graph. Use lexical for exact names, "
            "vector for concepts, "
            f"and graph for dependencies or relationships. Question: {question}"
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ollama_base_url, timeout=60
            ) as client:
                response = await client.post("/api/chat", json={
                    "model": self.settings.chat_model,
                    "stream": False,
                    "format": "json",
                    "messages": [{"role": "user", "content": prompt}],
                })
                response.raise_for_status()
                content = response.json()["message"]["content"]
            plan = QueryPlan.model_validate_json(content)
            required = self._fallback(question).tools
            return QueryPlan(tools=list(dict.fromkeys([*required, *plan.tools])))
        except Exception:
            return self._fallback(question)

    @staticmethod
    def _fallback(question: str) -> QueryPlan:
        tools: list[ToolName] = []
        if re.search(r"[A-Za-z_]\w*(?:\(\)|Service|Queue|Redis)", question) or re.search(
            r"\b[a-z]+[A-Z][A-Za-z]*\b", question
        ):
            tools.append("lexical")
        if re.search(r"depend|use|relationship|connect|call", question, re.IGNORECASE):
            tools.append("graph")
        if not tools or re.search(r"how|why|recover|explain", question, re.IGNORECASE):
            tools.append("vector")
        return QueryPlan(tools=list(dict.fromkeys(tools)))


class QueryState(TypedDict, total=False):
    question: str
    plan: QueryPlan
    candidates: list[EvidenceCandidate]
    events: list[dict]
    refinement_used: bool
    query_run_id: str


class BoundedQueryWorkflow:
    def __init__(
        self,
        engine: AsyncEngine,
        settings: Settings,
        planner: Planner | None = None,
        tools: dict[ToolName, Tool] | None = None,
    ):
        self.engine = engine
        self.planner = planner or OllamaPlanner(settings)
        self.tools = tools or {
            "lexical": lambda question: lexical_search(engine, question),
            "vector": lambda question: vector_search(engine, settings, question),
            "graph": lambda question: graph_search(engine, question),
        }
        graph = StateGraph(QueryState)
        graph.add_node("analyze", self._analyze)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("refine_once", self._refine_once)
        graph.add_node("persist", self._persist)
        graph.add_edge(START, "analyze")
        graph.add_edge("analyze", "retrieve")
        graph.add_conditional_edges(
            "retrieve", self._should_refine, {"refine": "refine_once", "persist": "persist"}
        )
        graph.add_edge("refine_once", "persist")
        graph.add_edge("persist", END)
        self.graph = graph.compile()

    async def run(self, question: str) -> dict:
        state = await self.graph.ainvoke({
            "question": question,
            "events": [],
            "refinement_used": False,
        })
        return {
            "query_run_id": state["query_run_id"],
            "question": question,
            "plan": state["plan"].model_dump(),
            "events": state["events"],
            "candidates": [candidate.as_dict() for candidate in state["candidates"]],
        }

    async def _analyze(self, state: QueryState) -> QueryState:
        plan = await self.planner.plan(state["question"])
        return {
            "plan": plan,
            "events": state["events"] + [{"node": "analyze", "tools": plan.tools}],
        }

    async def _retrieve(self, state: QueryState) -> QueryState:
        selected = [self.tools[name](state["question"]) for name in state["plan"].tools]
        result_sets = await asyncio.gather(*selected)
        candidates = reciprocal_rank_fusion(*result_sets)
        return {
            "candidates": candidates,
            "events": state["events"] + [{
                "node": "retrieve",
                "tools": state["plan"].tools,
                "candidate_count": len(candidates),
            }],
        }

    @staticmethod
    def _should_refine(state: QueryState) -> str:
        return "refine" if not state["candidates"] and not state["refinement_used"] else "persist"

    async def _refine_once(self, state: QueryState) -> QueryState:
        result = await self.tools["lexical"](state["question"])
        return {
            "candidates": result[:12],
            "refinement_used": True,
            "events": state["events"] + [{
                "node": "refine_once",
                "tool": "lexical",
                "candidate_count": len(result[:12]),
            }],
        }

    async def _persist(self, state: QueryState) -> QueryState:
        async with self.engine.begin() as connection:
            query_run = await connection.execute(text("""
                INSERT INTO query_runs (question) VALUES (:question) RETURNING id
            """), {"question": state["question"]})
            query_run_id = str(query_run.scalar_one())
            for rank, candidate in enumerate(state["candidates"], 1):
                if candidate.kind == "relationship":
                    await connection.execute(text("""
                        INSERT INTO evidence (query_run_id, relationship_id, rank)
                        VALUES (CAST(:run_id AS uuid), CAST(:evidence_id AS uuid), :rank)
                    """), {
                        "run_id": query_run_id,
                        "evidence_id": candidate.candidate_id.removeprefix("relationship:"),
                        "rank": rank,
                    })
                else:
                    await connection.execute(text("""
                        INSERT INTO evidence (query_run_id, chunk_id, rank)
                        VALUES (CAST(:run_id AS uuid), CAST(:evidence_id AS uuid), :rank)
                    """), {
                        "run_id": query_run_id,
                        "evidence_id": candidate.candidate_id,
                        "rank": rank,
                    })
        return {
            "query_run_id": query_run_id,
            "events": state["events"] + [{
                "node": "persist", "query_run_id": query_run_id,
            }],
        }
