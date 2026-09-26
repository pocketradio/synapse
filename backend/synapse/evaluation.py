from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

from synapse.config import get_settings
from synapse.retrieval import (
    EvidenceCandidate,
    graph_search,
    lexical_search,
    reciprocal_rank_fusion,
    retrieve,
    vector_search,
)
from synapse.routing import route_question
from synapse.workflow import BoundedQueryWorkflow, OllamaPlanner

BENCHMARK_PATH = Path(__file__).parents[1] / "evaluation" / "benchmark.json"
STRATEGIES = (
    "lexical", "vector", "hybrid", "hybrid_graph", "deterministic", "agent_selected"
)


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    question: str
    expected_sources: tuple[str, ...]
    answerable: bool


def load_benchmark(path: Path = BENCHMARK_PATH) -> list[BenchmarkCase]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [BenchmarkCase(
        id=item["id"],
        category=item["category"],
        question=item["question"],
        expected_sources=tuple(item["expected_sources"]),
        answerable=item["answerable"],
    ) for item in items]


def source_matches(actual: str, expected: str) -> bool:
    return actual.lower().endswith(expected.lower()) or expected.lower() in actual.lower()


def relevant(candidate: dict[str, Any], case: BenchmarkCase) -> bool:
    return any(
        source_matches(candidate.get("source_name", ""), source)
        for source in case.expected_sources
    )


def score_ranking(candidates: list[dict[str, Any]], case: BenchmarkCase) -> dict[str, float]:
    hits = [index for index, candidate in enumerate(candidates) if relevant(candidate, case)]
    return {
        "recall_at_5": float(any(index < 5 for index in hits)),
        "recall_at_10": float(any(index < 10 for index in hits)),
        "mrr": 1 / (hits[0] + 1) if hits else 0.0,
    }


def summarize_scores(
    scores: list[dict[str, float]], latencies: list[float]
) -> dict[str, float | None]:
    if not scores:
        return {"recall_at_5": None, "recall_at_10": None, "mrr": None, "median_latency_ms": None}
    return {
        "recall_at_5": round(statistics.mean(item["recall_at_5"] for item in scores), 4),
        "recall_at_10": round(statistics.mean(item["recall_at_10"] for item in scores), 4),
        "mrr": round(statistics.mean(item["mrr"] for item in scores), 4),
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
    }


def score_answer(result: dict[str, Any], case: BenchmarkCase) -> dict[str, float]:
    verification = result.get("verification", [])
    claims_with_citations = [item for item in verification if item.get("evidence_ids")]
    supported = [item for item in verification if item.get("status") == "supported"]
    answer = result.get("answer", "").lower()
    abstained = "cannot answer" in answer or not any(
        item.get("status") in {"supported", "partial"} for item in verification
    )
    return {
        "citation_precision": float(
            all(item.get("evidence_ids") for item in claims_with_citations)
        ) if claims_with_citations else 0.0,
        "citation_recall": float(bool(claims_with_citations)) if case.answerable else 1.0,
        "supported_claim_rate": len(supported) / len(verification) if verification else 0.0,
        "correct_abstention": float(abstained == (not case.answerable)),
        "model_calls": float(sum(
            bool(event.get("model_call")) for event in result.get("events", [])
        )),
        "model_error": float(any(event.get("error") for event in result.get("events", []))),
    }


def summarize_answers(
    scores: list[dict[str, float]], latencies: list[float]
) -> dict[str, float | None]:
    if not scores:
        return {"citation_precision": None, "citation_recall": None,
                "supported_claim_rate": None, "correct_abstention": None,
                "median_latency_ms": None, "median_model_calls": None,
                "model_error_rate": None}
    return {
        "citation_precision": round(
            statistics.mean(item["citation_precision"] for item in scores), 4
        ),
        "citation_recall": round(
            statistics.mean(item["citation_recall"] for item in scores), 4
        ),
        "supported_claim_rate": round(
            statistics.mean(item["supported_claim_rate"] for item in scores), 4
        ),
        "correct_abstention": round(
            statistics.mean(item["correct_abstention"] for item in scores), 4
        ),
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "median_model_calls": round(statistics.median(item["model_calls"] for item in scores), 2),
        "model_error_rate": round(statistics.mean(item["model_error"] for item in scores), 4),
    }


async def run_answer_benchmark(
    engine: Any, settings: Any, cases: list[BenchmarkCase] | None = None
) -> dict[str, Any]:
    cases = cases or load_benchmark()
    workflow = BoundedQueryWorkflow(engine, settings)
    limiter = asyncio.Semaphore(1)

    async def run_case(case: BenchmarkCase) -> tuple[dict[str, float], float]:
        async with limiter:
            started = time.perf_counter()
            result = await workflow.run(case.question)
            return score_answer(result, case), (time.perf_counter() - started) * 1000

    results = await asyncio.gather(*(run_case(case) for case in cases))
    scores = [score for score, _ in results]
    latencies = [latency for _, latency in results]
    return {
        "questions": len(cases),
        "answer_mode": settings.answer_mode,
        "answer_workflow": summarize_answers(scores, latencies),
    }


async def agent_selected_retrieve(engine: Any, settings: Any, question: str) -> dict[str, Any]:
    plan = await OllamaPlanner(settings).plan(question)
    tools = {
        "lexical": lambda: lexical_search(engine, question),
        "vector": lambda: vector_search(engine, settings, question),
        "graph": lambda: graph_search(engine, question),
    }
    selected = await asyncio.gather(*(tools[name]() for name in plan.tools))
    candidates: list[EvidenceCandidate] = reciprocal_rank_fusion(*selected)
    return {
        "strategy": "agent_selected",
        "tools": plan.tools,
        "candidates": [candidate.as_dict() for candidate in candidates],
    }


async def deterministic_retrieve(engine: Any, settings: Any, question: str) -> dict[str, Any]:
    decision = route_question(question)
    return await retrieve(
        engine,
        settings,
        question,
        strategy=decision.kind,
        selected_tools=decision.tools,
    )


async def run_benchmark(
    engine: Any, settings: Any, cases: list[BenchmarkCase] | None = None
) -> dict[str, Any]:
    cases = cases or load_benchmark()
    report: dict[str, Any] = {"questions": len(cases), "strategies": {}}
    for strategy in STRATEGIES:
        limiter = asyncio.Semaphore(4)

        async def run_case(
            case: BenchmarkCase,
            current_strategy: str = strategy,
            current_limiter: asyncio.Semaphore = limiter,
        ) -> tuple[dict[str, float], float]:
            async with current_limiter:
                started = time.perf_counter()
                result = (
                    await agent_selected_retrieve(engine, settings, case.question)
                    if current_strategy == "agent_selected"
                    else await deterministic_retrieve(engine, settings, case.question)
                    if current_strategy == "deterministic"
                    else await retrieve(engine, settings, case.question, current_strategy)
                )
                latency = (time.perf_counter() - started) * 1000
                return score_ranking(result["candidates"], case), latency

        results = await asyncio.gather(*(run_case(case) for case in cases))
        scores = [score for score, _ in results]
        latencies = [latency for _, latency in results]
        report["strategies"][strategy] = summarize_scores(scores, latencies)
    report["note"] = (
        "Gold evidence is matched by source name; generation metrics require an agent run."
    )
    return report


async def main(
    output: Path | None,
    answers_only: bool,
    limit: int | None,
    answer_mode: str | None,
) -> None:
    settings = get_settings()
    if answer_mode:
        settings = settings.model_copy(update={"answer_mode": answer_mode})
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        cases = load_benchmark()[:limit] if limit else None
        report = (
            await run_answer_benchmark(engine, settings, cases)
            if answers_only
            else await run_benchmark(engine, settings, cases)
        )
    finally:
        await engine.dispose()
    rendered = json.dumps(report, indent=2)
    if output:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Synapse retrieval benchmark.")
    parser.add_argument("--output", type=Path, help="also write the JSON report to this path")
    parser.add_argument("--answers-only", action="store_true")
    parser.add_argument("--limit", type=int, help="run only the first N benchmark questions")
    parser.add_argument(
        "--answer-mode",
        choices=("one_call", "risk_based", "two_call"),
        help="answer workflow mode for answer benchmarks",
    )
    args = parser.parse_args()
    asyncio.run(main(args.output, args.answers_only, args.limit, args.answer_mode))
