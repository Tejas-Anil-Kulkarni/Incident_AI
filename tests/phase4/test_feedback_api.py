import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
from agent.root_cause_analyzer import RootCauseAnalyzer, get_root_cause_analyzer
from backend.database import Base, get_db
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.fake_memory import FakeMemory
from learning.models import ActionSimulation, FeedbackRecord
from main import app


class CountingMemory(FakeMemory):
    def __init__(self):
        super().__init__()
        self.retain_calls = 0

    async def retain_incident(self, incident):
        self.retain_calls += 1
        return await super().retain_incident(incident)


class EvidenceDrivenLLM:
    async def complete_json(self, *, model, messages):
        prompt = json.loads(messages[1]["content"])
        recalled_id = prompt["recalled_evidence"][0]["incident_id"]
        return json.dumps({
            "hypotheses": [{
                "cause": "Database sessions were not closed",
                "evidence_incident_ids": [recalled_id],
                "reasoning": "A resolved incident for this service recorded the same pool timeout.",
                "status": "suspected",
            }],
            "recommended_steps": ["Inspect database pool metrics"],
            "runbook_ref": "runbooks/database_failure.md",
        })


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    memory = CountingMemory()

    def override_get_db():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory_store] = lambda: memory
    app.dependency_overrides[get_root_cause_analyzer] = lambda: RootCauseAnalyzer(memory, EvidenceDrivenLLM())
    with TestClient(app) as test_client:
        test_client.memory = memory
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def post_incident(client, *, error="database connection pool exhausted"):
    return client.post("/incidents", json={
        "service": "payments-api",
        "error": error,
        "status": "degraded",
        "logs": "Timeout waiting for database connection from pool",
    }).json()


def test_feedback_is_idempotent_and_retains_verified_incident_once(client):
    incident = post_incident(client)
    payload = {
        "suspected_cause": "Possible database pool saturation",
        "verified_cause": "unclosed sessions exhausted the pool",
        "steps_taken": ["Fix session cleanup"],
        "outcome": "resolved",
        "notes": "Confirmed by engineer",
    }
    first = client.post(f"/incidents/{incident['id']}/feedback", json=payload)
    duplicate = client.post(f"/incidents/{incident['id']}/feedback", json=payload)
    assert first.status_code == 200
    assert first.json()["memory_retained"] is True
    assert duplicate.json()["duplicate"] is True
    assert client.memory.retain_calls == 1
    retained = client.memory._records[incident["id"]]
    assert retained.suspected_cause == payload["suspected_cause"]
    assert retained.verified_cause == payload["verified_cause"]
    assert retained.outcome == "resolved"


def test_failed_feedback_returns_warning_and_is_surfaced_in_later_analysis(client):
    first_incident = post_incident(client)
    response = client.post(f"/incidents/{first_incident['id']}/feedback", json={
        "verified_cause": "upstream pool was misconfigured",
        "steps_taken": ["Increase connection timeout"],
        "outcome": "failed",
        "notes": "Timeouts increased after the change",
    })
    assert response.json()["warning"]

    second_incident = post_incident(client, error="Payment API database connection pool timeout")
    analyzed = client.post(f"/incidents/{second_incident['id']}/analyze").json()
    assert any(first_incident["id"] in warning and "ended in failure" in warning for warning in analyzed["warnings"])


def test_feedback_stats_route_uses_saved_outcomes(client):
    for index, outcome in enumerate(("resolved", "resolved", "failed")):
        incident = post_incident(client, error=f"database connection pool exhausted {index}")
        response = client.post(f"/incidents/{incident['id']}/feedback", json={
            "verified_cause": "unclosed sessions",
            "steps_taken": ["Fix cleanup"],
            "outcome": outcome,
        })
        assert response.status_code == 200
    stats = client.get("/stats/outcomes").json()
    assert stats["total_recorded"] == 3
    assert stats["outcomes"] == {"resolved": 2, "failed": 1, "partial": 0}
    assert stats["by_resolution"][0]["display"] == "2 of 3 recorded"


def test_action_requires_approval_and_only_logs_a_simulation(client):
    incident = post_incident(client)
    incident_id = incident["id"]
    action = {"action_id": "restart-workers", "action": "Restart the affected workers", "approved_by": "engineer@example.test"}
    assert client.post(f"/incidents/{incident_id}/execute-action", json={"action_id": "restart-workers"}).status_code == 409
    approval = client.post(f"/incidents/{incident_id}/approve-action", json=action)
    assert approval.status_code == 200
    result = client.post(f"/incidents/{incident_id}/execute-action", json={"action_id": "restart-workers"})
    assert result.status_code == 200
    assert result.json()["status"] == "simulated"
    assert result.json()["executed"] is False
    with client.test_session() as session:
        records = session.scalars(select(ActionSimulation)).all()
        assert len(records) == 1
        assert records[0].action == action["action"]


def test_feedback_records_are_persisted(client):
    incident = post_incident(client)
    client.post(f"/incidents/{incident['id']}/feedback", json={
        "verified_cause": "bad pool configuration",
        "steps_taken": ["Restore known-good pool config"],
        "outcome": "partial",
        "notes": "Service recovered partially",
    })
    with client.test_session() as session:
        rows = session.scalars(select(FeedbackRecord)).all()
        assert rows[0].notes == "Service recovered partially"
        assert json.loads(rows[0].steps_json) == ["Restore known-good pool config"]


def test_learning_story_cites_verified_fix_and_ranks_it_first(client):
    first_incident = post_incident(client)
    feedback = client.post(f"/incidents/{first_incident['id']}/feedback", json={
        "suspected_cause": "Possible database pool exhaustion",
        "verified_cause": "unclosed sessions exhausted the connection pool",
        "steps_taken": ["Close sessions in the request finally block"],
        "outcome": "resolved",
    })
    assert feedback.status_code == 200

    second_incident = post_incident(client, error="Payment API timeout waiting for a database connection")
    result = client.post(f"/incidents/{second_incident['id']}/analyze").json()
    assert first_incident["id"] in result["analysis"]["hypotheses"][0]["evidence_incident_ids"]
    assert result["analysis"]["recommended_steps"][0] == (
        f"Previously successful in incident {first_incident['id']}: Close sessions in the request finally block"
    )
