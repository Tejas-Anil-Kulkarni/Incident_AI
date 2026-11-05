import pytest
from pydantic import ValidationError

from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident


def sample(**overrides):
    values = {
        "id": "db-1",
        "service": "payments-api",
        "error": "connection pool exhausted",
        "severity": "high",
        "symptoms": ["timeout", "pool saturation"],
        "logs_excerpt": "Timeout waiting for database connection",
        "outcome": "resolved",
        "verified_cause": "sessions leaked",
        "resolution_steps": ["close sessions"],
    }
    values.update(overrides)
    return Incident.model_validate(values)


@pytest.mark.asyncio
async def test_retain_then_recall_returns_incident() -> None:
    memory = FakeMemory()
    incident = sample()
    result = await memory.retain_incident(incident)
    recalled = await memory.recall_similar("payments API connection pool timeout")
    assert result.success
    assert recalled
    assert recalled[0].incident_id == incident.id
    assert "sessions leaked" in recalled[0].raw_text


@pytest.mark.asyncio
async def test_empty_memory_returns_empty_list() -> None:
    assert await FakeMemory().recall_similar("nothing stored") == []


def test_malformed_incident_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate({"id": "x", "service": "", "error": "oops", "outcome": "unknown"})


@pytest.mark.asyncio
async def test_fake_reflect_is_grounded_in_stored_records() -> None:
    result = await FakeMemory([sample()]).reflect("payments pool timeout")
    assert "db-1" in result.raw_text
