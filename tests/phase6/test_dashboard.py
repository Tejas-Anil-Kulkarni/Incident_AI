from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from streamlit.testing.v1 import AppTest

import backend.database as database
from backend.database import Base, get_db
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.fake_memory import FakeMemory
from main import app


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(database, "engine", test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    memory = FakeMemory()

    def override_get_db():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory_store] = lambda: memory
    with TestClient(app) as test_client:
        test_client.test_session = test_session
        test_client.memory = memory
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def ingest(client, error="database pool timeout"):
    response = client.post("/incidents", json={
        "service": "payments-api", "error": error, "status": "degraded", "logs": "pool timeout",
    })
    assert response.status_code == 201
    return response.json()


def test_dashboard_read_only_endpoints_report_feed_and_confirmed_memory(client):
    older = ingest(client, "database pool timeout 1")
    newer = ingest(client, "database pool timeout 2")
    feedback = client.post(f"/incidents/{older['id']}/feedback", json={
        "verified_cause": "unclosed sessions", "steps_taken": ["Close sessions"],
        "outcome": "resolved", "notes": "Confirmed",
    })
    assert feedback.status_code == 200
    assert feedback.json()["memory_retained"] is True

    feed = client.get("/incidents?limit=1")
    assert feed.status_code == 200
    assert feed.json()[0]["incident"]["id"] == newer["id"]
    all_rows = client.get("/incidents").json()
    assert next(row for row in all_rows if row["incident"]["id"] == older["id"])["status"] == "verified"
    stats = client.get("/stats/memory").json()
    assert stats == {"feedback_records": 1, "retained_in_hindsight": 1}


def test_dashboard_read_only_endpoints_have_honest_empty_state(client):
    assert client.get("/incidents").json() == []
    assert client.get("/stats/memory").json() == {"feedback_records": 0, "retained_in_hindsight": 0}


def test_dashboard_app_renders_sections_and_api_error_state():
    dashboard_path = Path(__file__).resolve().parents[2] / "frontend" / "dashboard.py"
    app_test = AppTest.from_file(dashboard_path, default_timeout=30).run(timeout=30)
    assert not app_test.exception
    assert "Incident feed" in [item.value for item in app_test.header]
    assert "Replay Lab" in [item.label for item in app_test.tabs]
    assert "Learning and memory" in [item.value for item in app_test.header]
    assert any("Cannot reach IncidentMind API" in item.value for item in app_test.error)


def test_api_client_formats_backend_errors(monkeypatch):
    from urllib.error import HTTPError

    from frontend.api_client import ApiError, IncidentMindApi

    def fail(*args, **kwargs):
        raise HTTPError("http://api/incidents", 503, "unavailable", {}, None)

    monkeypatch.setattr("frontend.api_client.urlopen", fail)
    with pytest.raises(ApiError, match="HTTP 503"):
        IncidentMindApi("http://api").list_incidents()
