"""Regression contracts for all completed phases."""

from backend.api import health
from main import app


def test_phase0_health_contract_is_backward_compatible() -> None:
    operation = app.openapi()["paths"]["/health"]["get"]
    response = health().model_dump(mode="json")

    assert "200" in operation["responses"]
    assert set(response) == {"status", "timestamp"}
    assert response["status"] == "ok"
