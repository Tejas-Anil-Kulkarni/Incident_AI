from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
from agent.llm_client import GroqChatModel
from backend.database import Base, get_db
from main import app


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def alert(**overrides):
    payload = {
        "service": "payments-api",
        "error": "database connection pool exhausted",
        "status": "degraded",
        "logs": "Timeout waiting for a database connection",
    }
    payload.update(overrides)
    return payload


def test_huge_unicode_logs_are_bounded_and_preserved(client):
    logs = ("雪🙂 λ database timeout ERROR\n" * 6_500)[:180_000]
    response = client.post("/incidents", json=alert(
        service="支付-api",
        error="数据库连接池耗尽 🚨",
        logs=logs,
    ))
    assert response.status_code == 201
    incident = response.json()
    assert incident["service"] == "支付-api"
    assert incident["error"] == "数据库连接池耗尽 🚨"
    assert len(incident["logs_excerpt"]) == 50_000
    assert "雪🙂 λ" in incident["logs_excerpt"]


def test_logs_over_the_documented_limit_return_validation_error(client):
    response = client.post("/incidents", json=alert(logs="x" * 200_001))
    assert response.status_code == 422


def test_fifty_sequential_incidents_are_persisted_and_listed(client):
    ids = []
    for index in range(50):
        response = client.post("/incidents", json=alert(error=f"database pool exhausted request {index}"))
        assert response.status_code == 201
        ids.append(response.json()["id"])
    listed = client.get("/incidents?limit=100")
    assert listed.status_code == 200
    assert len(listed.json()) == 50
    assert {row["incident"]["id"] for row in listed.json()} == set(ids)


@pytest.mark.asyncio
async def test_groq_rate_limit_429_retries_then_recovers(monkeypatch):
    class RateLimitError(Exception):
        status_code = 429

    class CompletionEndpoint:
        def __init__(self):
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError("rate limited")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}', tool_calls=None))])

    endpoint = CompletionEndpoint()
    client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    model = GroqChatModel("test-key", client=client, retries=1)

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("agent.llm_client.asyncio.sleep", no_wait)
    result = await model.complete_json(model="qwen/qwen3-32b", messages=[])
    assert result == '{"ok":true}'
    assert endpoint.calls == 2
