import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
from backend.database import Base, get_db
from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident
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
    result = {
        "service": "payments-api",
        "error": "Database connection pool exhausted",
        "cpu_percent": 91,
        "failed_requests": 24,
        "status": "degraded",
        "logs": "sqlalchemy.exc.TimeoutError: connection pool exhausted\nFile \"db.py\", line 42, in connect",
    }
    result.update(overrides)
    return result


def test_create_get_and_not_found_routes(client):
    created = client.post("/incidents", json=alert())
    assert created.status_code == 201
    body = created.json()
    assert body["service"] == "payments-api"
    assert body["category"] == "Database"
    assert body["severity"] == "high"
    assert body["top_stack_frames"] == ['File "db.py", line 42, in connect']
    fetched = client.get(f"/incidents/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert client.get("/incidents/missing-id").status_code == 404


def test_invalid_alert_returns_validation_error(client):
    response = client.post("/incidents", json=alert(service="", cpu_percent=101))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_phase2_incident_can_be_retained_by_phase1_interface(client):
    response = client.post("/incidents", json=alert())
    incident = response.json()
    result = await FakeMemory().retain_incident(Incident.model_validate(incident))
    assert result.success
    assert result.incident_id == incident["id"]
