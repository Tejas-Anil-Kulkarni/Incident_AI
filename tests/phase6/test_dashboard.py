import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    verification = client.get(f"/incidents/{older['id']}/feedback")
    assert verification.status_code == 200
    assert verification.json()[0]["verified_cause"] == "unclosed sessions"
    assert verification.json()[0]["steps_taken"] == ["Close sessions"]
    assert verification.json()[0]["memory_retained"] is True

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
    incident = ingest(client)
    assert client.get(f"/incidents/{incident['id']}/feedback").json() == []
    assert client.get("/incidents/unknown/feedback").status_code == 404


def test_dashboard_react_entrypoint_and_fastapi_client_contract():
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    source = (frontend / "src" / "api.js").read_text(encoding="utf-8")
    html = (frontend / "index.html").read_text(encoding="utf-8")
    assert manifest["scripts"]["build"] == "vite build"
    assert '<div id="root"></div>' in html
    for route in ("/incidents?limit=", "/incidents/${encodeURIComponent(id)}/feedback", "/stats/memory", "/stats/memory/origins", "/stats/outcomes", "/innovation/replay", "/innovation/insights"):
        assert route in source


def test_api_client_formats_backend_errors(monkeypatch):
    from urllib.error import HTTPError

    from frontend.api_client import ApiError, IncidentMindApi

    def fail(*args, **kwargs):
        raise HTTPError("http://api/incidents", 503, "unavailable", {}, None)

    monkeypatch.setattr("frontend.api_client.urlopen", fail)
    with pytest.raises(ApiError, match="HTTP 503"):
        IncidentMindApi("http://api").list_incidents()
