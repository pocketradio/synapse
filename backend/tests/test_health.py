from synapse.health import overall_status


def service(status: str) -> dict[str, str]:
    return {"status": status}


def test_overall_health_requires_every_dependency() -> None:
    assert overall_status(service("healthy"), service("healthy")) == "healthy"


def test_overall_health_reports_partial_availability() -> None:
    assert overall_status(service("healthy"), service("unhealthy")) == "degraded"
    assert overall_status(service("degraded"), service("unhealthy")) == "degraded"


def test_overall_health_reports_total_failure() -> None:
    assert overall_status(service("unhealthy"), service("unhealthy")) == "unhealthy"

