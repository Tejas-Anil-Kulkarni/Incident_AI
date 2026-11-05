import os

import pytest

from config.settings import Settings
from hindsight_memory.hindsight_client import HindsightMemory
from hindsight_memory.models import Incident

pytestmark = pytest.mark.integration


def _settings_or_skip():
    required = ("HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL")
    if any(not os.getenv(key) for key in required):
        pytest.skip("Hindsight integration credentials are not configured")
    # Groq settings are irrelevant to the client wrapper; supply test placeholders.
    return Settings(
        HINDSIGHT_API_KEY=os.environ["HINDSIGHT_API_KEY"],
        HINDSIGHT_BASE_URL=os.environ["HINDSIGHT_BASE_URL"],
        GROQ_API_KEY=os.getenv("GROQ_API_KEY", "integration-not-used"),
        MODEL_NAME=os.getenv("MODEL_NAME", "integration-not-used"),
    )


@pytest.mark.asyncio
async def test_real_hindsight_retains_and_recalls_three_incidents():
    memory = await HindsightMemory.connect(_settings_or_skip())
    try:
        for index, service in enumerate(("payments-api", "catalog-api", "billing-api")):
            await memory.retain_incident(Incident(
                id=f"integration-db-pool-{index}",
                service=service,
                error="database connection pool exhausted with request timeouts",
                severity="high",
                symptoms=["connection timeout", "pool exhausted"],
                logs_excerpt="Timed out while waiting for an idle database connection",
                verified_cause="sessions leaked in the API worker",
                outcome="resolved",
                tags=["integration"],
            ))
        results = await memory.recall_similar("database pool exhaustion and connection timeout", k=5)
        assert any("pool" in item.raw_text.lower() for item in results)
    finally:
        await memory.close()
