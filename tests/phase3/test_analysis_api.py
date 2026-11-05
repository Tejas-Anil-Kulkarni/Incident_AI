import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
from agent.root_cause_analyzer import RootCauseAnalyzer, get_root_cause_analyzer
from backend.database import Base, get_db
from hindsight_memory.fake_memory import FakeMemory
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
    app.dependency_overrides[get_root_cause_analyzer] = lambda: RootCauseAnalyzer(FakeMemory(), None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_analyze_route_is_additive_and_handles_cold_start(client):
    created = client.post("/incidents", json={"service": "payments-api", "error": "database pool timeout"})
    incident_id = created.json()["id"]
    analysis = client.post(f"/incidents/{incident_id}/analyze")
    assert analysis.status_code == 200
    assert analysis.json()["incident_id"] == incident_id
    assert analysis.json()["cold_start"] is True
    assert "No relevant experience" in analysis.json()["message"]
    assert client.post("/incidents/missing/analyze").status_code == 404
