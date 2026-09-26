from synapse.answering import VerificationResult, render_answer, validate_citations


def test_invalid_citations_make_a_claim_unsupported() -> None:
    result = VerificationResult(
        claim_text="redis is the source of truth",
        evidence_ids=["missing"],
        status="supported",
    )
    checked = validate_citations([result], [{"evidence_id": "real"}])
    assert checked[0].status == "unsupported"
    assert checked[0].evidence_ids == []


def test_answer_abstains_when_no_claim_is_supported() -> None:
    result = VerificationResult(
        claim_text="unknown detail",
        evidence_ids=[],
        status="unsupported",
    )
    assert render_answer([result]) == "I cannot answer this from the available evidence."
