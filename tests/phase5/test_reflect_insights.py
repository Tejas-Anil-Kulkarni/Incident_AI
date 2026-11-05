import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
from backend.database import Base, get_db
from backend.models import IncidentRecord
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.models import ReflectResult
from innovation.models import ReflectInsightCache
from learning.models import FeedbackRecord
from main import app


class ReflectMemory:
    def __init__(self, *, fails=False):
        self.calls = 0
        self.fails = fails

    async def reflect(self, question):
        self.calls += 1
        if self.fails:
            raise RuntimeError("Reflect unavailable")
        return ReflectResult(answer="Hindsight insight", raw_text="raw evidence")


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    memory = ReflectMemory()

    def override_get_db():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory_store] = lambda: memory
    with TestClient(app) as test_client:
        test_client.memory = memory
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_reflect_result_is_cached_and_refresh_forces_new_reflection(client):
    payload = {"question": "What causes database failures?"}
    first = client.post("/innovation/insights", json=payload).json()
    second = client.post("/innovation/insights", json=payload).json()
    assert first["source"] == "hindsight"
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["cached_at"] == first["cached_at"]
    assert client.memory.calls == 1

    refreshed = client.post("/innovation/insights", json={**payload, "refresh": True}).json()
    assert refreshed["cached"] is False
    assert client.memory.calls == 2


def test_reflect_failure_uses_grounded_feedback_and_persists_fallback(client):
    incident_id = "inc-failed-001"
    incident = {
        "id": incident_id,
        "service": "payments-api",
        "error": "database pool timeout",
        "severity": "high",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with client.test_session() as session:
        session.add(IncidentRecord(
            id=incident_id, service="payments-api", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            signature="db-timeout", payload_json=json.dumps(incident),
        ))
        session.add(FeedbackRecord(
            feedback_id="feedback-1", incident_id=incident_id,
            verified_cause="pool was already saturated", outcome="failed",
            steps_json=json.dumps(["Increase connection timeout"]),
            notes="Timeouts increased after the change", memory_retained=False,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        session.commit()

    client.memory.fails = True
    payload = {"question": "Which fixes failed?"}
    response = client.post("/innovation/insights", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "sqlite_fallback"
    assert data["success"] is False
    assert incident_id in data["answer"]
    assert "Increase connection timeout" in data["answer"]
    assert "Timeouts increased after the change" in data["answer"]
    with client.test_session() as session:
        cached = session.scalars(select(ReflectInsightCache)).one()
        assert cached.source == "sqlite_fallback"
        assert cached.created_at is not None

    again = client.post("/innovation/insights", json=payload).json()
    assert again["cached"] is True
    assert again["answer"] == data["answer"]
    assert client.memory.calls == 1


def test_fallback_is_explicit_when_no_feedback_exists(client):
    client.memory.fails = True
    result = client.post("/innovation/insights", json={"question": "Summarize recorded fixes"}).json()
    assert result["source"] == "sqlite_fallback"
    assert result["success"] is False
    assert result["answer"] == "No engineer feedback has been recorded in SQLite."
