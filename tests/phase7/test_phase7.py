from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.api as api
import backend.database as database
from agent.root_cause_analyzer import RootCauseAnalyzer
from backend.database import Base, get_db
from backend.models import IncidentRecord
from config.settings import FeatureFlags
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident, MemoryEvidence
from main import app
from learning.outcome_stats import FeedbackEntry, compute_outcome_stats
from learning.models import FeedbackRecord
from innovation.deploy_risk import build_deploy_risk_response
from innovation.staleness import find_staleness_conflicts


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    memory = FakeMemory()
    monkeypatch.setattr(api, "get_feature_flags", lambda: SimpleNamespace(
        chaos_dojo_enabled=True, staleness_enabled=True, deploy_risk_enabled=True,
    ))

    def override_get_db():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory_store] = lambda: memory
    app.dependency_overrides[api.get_root_cause_analyzer] = lambda: RootCauseAnalyzer(memory, None)
    with TestClient(app) as test_client:
        test_client.memory = memory
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def _incident(incident_id, *, day, cause, signature="pool-timeout", tags=None):
    return Incident(
        id=incident_id,
        service="payments-api",
        error="connection pool timeout waiting for database connection",
        severity="high",
        symptoms=["database pool timeout"],
        signature=signature,
        category="Database",
        verified_cause=cause,
        created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        tags=tags or [],
    )


def test_chaos_dojo_marks_synthetic_stores_feedback_and_excludes_stats(client):
    result = client.post("/innovation/chaos-dojo", json={"fault": "database_pool", "service": "demo-payments"})
    assert result.status_code == 200
    data = result.json()
    assert data["synthetic"] is True
    assert "synthetic=true" in data["incident"]["tags"]
    assert data["scripted_feedback"]["outcome"] == "resolved"
    assert data["scripted_feedback"]["memory_retained"] is True
    retained = client.memory._records[data["incident"]["id"]]
    assert retained.outcome == "resolved"
    assert "synthetic=true" in retained.tags
    assert client.get("/stats/outcomes").json()["total_recorded"] == 0
    assert client.get("/stats/memory/origins").json() == {
        "real_feedback_records": 0,
        "real_retained_in_hindsight": 0,
        "synthetic_feedback_records": 1,
        "synthetic_retained_in_hindsight": 1,
    }
    feed_row = client.get("/incidents").json()[0]
    assert feed_row["synthetic"] is True
    assert feed_row["status"] == "synthetic"


def test_staleness_flags_older_conflicting_verified_memory_and_keeps_both():
    older = _incident("older", day=1, cause="pool configuration was too small")
    newer = _incident("newer", day=2, cause="deployment leaked database sessions")
    result = find_staleness_conflicts(
        [newer, older],
        {"older": older.verified_cause, "newer": newer.verified_cause},
    )
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.older_incident_id == "older"
    assert conflict.newer_incident_id == "newer"
    assert conflict.older_verified_cause == older.verified_cause
    assert conflict.newer_verified_cause == newer.verified_cause
    assert conflict.status == "possibly outdated"


def test_staleness_endpoint_returns_conflicts_for_requested_incident(client):
    older = _incident("older-api", day=1, cause="pool configuration was too small")
    newer = _incident("newer-api", day=2, cause="deployment leaked database sessions")
    with client.test_session() as session:
        for item in (older, newer):
            session.add(IncidentRecord(
                id=item.id,
                service=item.service,
                created_at=item.created_at,
                signature=item.signature,
                payload_json=item.model_dump_json(),
            ))
            session.add(FeedbackRecord(
                feedback_id=f"feedback-{item.id}",
                incident_id=item.id,
                verified_cause=item.verified_cause,
                outcome="resolved",
                steps_json=json.dumps(["check pool"]),
                created_at=item.created_at,
                memory_retained=False,
            ))
        session.commit()
    result = client.get("/incidents/older-api/staleness")
    assert result.status_code == 200
    assert [(item["older_incident_id"], item["newer_incident_id"]) for item in result.json()["conflicts"]] == [
        ("older-api", "newer-api"),
    ]


def test_staleness_ignores_synthetic_or_dissimilar_records():
    old = _incident("old", day=1, cause="old cause")
    synthetic = _incident("synthetic", day=2, cause="new cause", tags=["synthetic=true"])
    unrelated = _incident("unrelated", day=3, cause="other cause", signature="different-signature").model_copy(
        update={"error": "filesystem checksum mismatch", "symptoms": ["disk corruption"]}
    )
    result = find_staleness_conflicts(
        [old, synthetic, unrelated],
        {item.id: item.verified_cause for item in (old, synthetic, unrelated)},
    )
    assert result.conflicts == []


def test_deploy_risk_splits_synthetic_and_real_evidence_without_score():
    real = _incident("real-1", day=1, cause="pool leak")
    synthetic = _incident("synthetic-1", day=2, cause="load spike", tags=["synthetic=true"])
    from hindsight_memory.memory_retain import incident_content

    evidence = [
        MemoryEvidence(text=incident_content(item), raw_text=incident_content(item), incident_id=item.id)
        for item in (real, synthetic)
    ]
    response = build_deploy_risk_response(evidence, available=True, change_description="rotate DB connection pool")
    assert [item.incident_id for item in response.historical_evidence] == ["real-1"]
    assert [item.incident_id for item in response.synthetic_evidence] == ["synthetic-1"]
    assert "probability" in response.message
    assert "score" not in response.model_dump()


def test_deploy_risk_returns_safe_empty_response_without_memory(client, monkeypatch):
    app.dependency_overrides[get_memory_store] = lambda: None
    response = client.post("/innovation/deploy-risk", json={"change_description": "rotate database connection settings"})
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["historical_evidence"] == []
    assert response.json()["synthetic_evidence"] == []


def test_synthetic_entries_do_not_affect_outcome_stats():
    stats = compute_outcome_stats([
        FeedbackEntry(incident_id="real", verified_cause="pool leak", outcome="resolved"),
        FeedbackEntry(incident_id="synthetic", verified_cause="sample", outcome="resolved", synthetic=True),
    ])
    assert stats.total_recorded == 1
    assert stats.outcomes["resolved"] == 1


def test_phase7_flags_default_off_and_routes_stay_disabled(client, monkeypatch):
    defaults = FeatureFlags(_env_file=None)
    assert defaults.chaos_dojo_enabled is False
    assert defaults.staleness_enabled is False
    assert defaults.deploy_risk_enabled is False
    monkeypatch.setattr(api, "get_feature_flags", lambda: defaults)
    assert client.post("/innovation/chaos-dojo", json={"fault": "database_pool"}).status_code == 404
    assert client.get("/incidents/unknown/staleness").status_code == 404
    assert client.post("/innovation/deploy-risk", json={
        "change_description": "rotate database connection settings",
    }).status_code == 404
