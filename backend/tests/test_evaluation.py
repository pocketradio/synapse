from synapse.cache import RetrievalCache
from synapse.evaluation import (
    BenchmarkCase,
    load_benchmark,
    score_answer,
    score_ranking,
    summarize_scores,
)
from synapse.routing import route_question


def test_benchmark_contains_twenty_cases() -> None:
    cases = load_benchmark()
    assert len(cases) == 20
    assert sum(not case.answerable for case in cases) == 3


def test_ranking_metrics_use_gold_source_names() -> None:
    case = BenchmarkCase("q", "exact lookup", "where", ("payment_service.py",), True)
    candidates = [
        {"source_name": "architecture.md"},
        {"source_name": "payment_service.py"},
    ]
    assert score_ranking(candidates, case) == {
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr": 0.5,
    }


def test_empty_scores_are_reported_as_unavailable() -> None:
    assert summarize_scores([], []) == {
        "recall_at_5": None,
        "recall_at_10": None,
        "mrr": None,
        "median_latency_ms": None,
    }


def test_answer_metrics_reward_citations_and_correct_abstention() -> None:
    answerable = BenchmarkCase("q", "exact lookup", "where", ("a.md",), True)
    result = {
        "answer": "the answer",
        "verification": [{"status": "supported", "evidence_ids": ["e1"]}],
        "events": [
            {"node": "analyze", "model_call": False},
            {"node": "generate_claims", "model_call": True},
        ],
    }
    metrics = score_answer(result, answerable)
    assert metrics["citation_precision"] == 1.0
    assert metrics["supported_claim_rate"] == 1.0
    assert metrics["model_calls"] == 1.0

    unanswerable = BenchmarkCase("q", "unanswerable", "unknown", (), False)
    abstained = {"answer": "I cannot answer this from the available evidence."}
    assert score_answer(abstained, unanswerable)["correct_abstention"] == 1.0


def test_routes_exact_identifier_without_model_work() -> None:
    route = route_question("Where is processPayment() implemented?")
    assert route.kind == "exact"
    assert route.tools == ["lexical"]
    assert route.generate_answer is False
    assert route.verify_answer is False


def test_routes_relationship_explanation_to_all_relevant_tools() -> None:
    route = route_question("How does CheckoutService depend on Redis?")
    assert route.kind == "relationship"
    assert route.tools == ["lexical", "vector", "graph"]


def test_routes_uncertain_questions_to_hybrid() -> None:
    route = route_question("What is the checkout setting?")
    assert route.kind == "hybrid"
    assert route.tools == ["lexical", "vector", "graph"]


def test_cache_normalization_makes_whitespace_and_case_reusable() -> None:
    assert RetrievalCache.normalize("  Where  IS checkout? ") == "where is checkout?"

