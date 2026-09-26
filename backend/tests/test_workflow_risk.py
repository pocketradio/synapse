from synapse.answering import VerificationResult
from synapse.workflow import QueryPlan, calculate_risk_score


def test_strong_evidence_has_no_risk() -> None:
    plan = QueryPlan(kind="semantic", tools=["vector"])
    evidence = [
        {"source_name": "architecture.md", "evidence_id": "one"},
        {"source_name": "service_config.json", "evidence_id": "two"},
    ]
    results = [VerificationResult(
        claim_text="redis is used",
        evidence_ids=["one"],
        status="supported",
    )]

    assert calculate_risk_score(plan, evidence, results) == 0


def test_conflict_and_missing_citation_raise_risk() -> None:
    plan = QueryPlan(kind="relationship", tools=["graph"])
    evidence = [{"source_name": "architecture.md", "evidence_id": "one"}]
    results = [
        VerificationResult(
            claim_text="retries are enabled",
            evidence_ids=[],
            status="conflicting",
        )
    ]

    assert calculate_risk_score(plan, evidence, results) >= 4
