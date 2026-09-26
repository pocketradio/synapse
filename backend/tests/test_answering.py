from synapse.answering import (
    Claim,
    VerificationResult,
    parse_claims,
    render_answer,
    validate_citations,
    validate_claims,
)


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


def test_invalid_claim_citations_are_removed_before_verification() -> None:
    claim = Claim(claim_text="redis is used", evidence_ids=["missing", "real"])

    checked = validate_claims([claim], [{"evidence_id": "real"}])

    assert checked[0].evidence_ids == ["real"]


def test_single_claim_response_is_normalized() -> None:
    claims = parse_claims({"claim_text": "redis is used", "evidence_ids": ["real"]})

    assert len(claims) == 1
    assert claims[0].claim_text == "redis is used"
