from types import SimpleNamespace

import pytest

from hindsight_memory.hindsight_client import HindsightMemory
from hindsight_memory.models import Incident


def incident() -> Incident:
    return Incident(id="failure-1", service="api", error="timeout", severity="high")


class FlakyClient:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def retain(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("simulated")
        return SimpleNamespace()

    def recall(self, **kwargs):
        return SimpleNamespace(results=[SimpleNamespace(text="api timeout memory", id="m1", score=0.9)])

    def reflect(self, **kwargs):
        return SimpleNamespace(text="One prior API timeout was resolved.")


@pytest.mark.asyncio
async def test_timeout_retries_then_falls_back_without_exposing_exception() -> None:
    client = FlakyClient(failures=8)
    memory = HindsightMemory(client, retries=1, backoff_seconds=0)
    result = await memory.retain_incident(incident())
    assert not result.success
    assert result.error == "Hindsight memory is temporarily unavailable."
    assert client.calls == 2


@pytest.mark.asyncio
async def test_transient_timeout_retries_and_recovers() -> None:
    client = FlakyClient(failures=1)
    memory = HindsightMemory(client, retries=1, backoff_seconds=0)
    result = await memory.retain_incident(incident())
    assert result.success
    assert client.calls == 2


@pytest.mark.asyncio
async def test_recall_and_reflect_adapt_official_response_shapes() -> None:
    memory = HindsightMemory(FlakyClient(failures=0))
    recalled = await memory.recall_similar("api timeout", 2)
    reflected = await memory.reflect("what happened with API timeouts?")
    assert recalled[0].raw_text == "api timeout memory"
    assert reflected.answer.startswith("One prior")


@pytest.mark.asyncio
async def test_recall_keeps_official_source_chunk_for_evidence_grounding() -> None:
    response = SimpleNamespace(
        results=[SimpleNamespace(text="sessions leaked", id="memory-1", chunk_id="chunk-1")],
        chunks={"chunk-1": SimpleNamespace(text='IncidentMind incident record:\n{"id":"incident-7"}')},
    )

    class ChunkClient(FlakyClient):
        def recall(self, **kwargs):
            assert kwargs["include_chunks"] is True
            return response

    result = await HindsightMemory(ChunkClient(failures=0)).recall_similar("session leak")
    assert result[0].raw_text == "sessions leaked"
    assert '"id":"incident-7"' in result[0].source_text
