from backend.api import health
from main import app


def test_health_returns_stable_contract() -> None:
    operation = app.openapi()["paths"]["/health"]["get"]
    body = health().model_dump(mode="json")

    assert "200" in operation["responses"]
    assert body["status"] == "ok"
    assert "timestamp" in body

