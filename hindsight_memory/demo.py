"""CLI demonstration of official Hindsight Retain followed by Recall."""

import asyncio

from config.settings import get_settings
from hindsight_memory.hindsight_client import HindsightMemory
from hindsight_memory.models import Incident


async def main() -> None:
    memory = await HindsightMemory.connect(get_settings())
    incident = Incident(
        id="demo-connection-pool-001",
        service="payments-api",
        error="Database connection pool exhausted",
        severity="high",
        symptoms=["request timeouts", "connection acquisition failures"],
        logs_excerpt="Timeout waiting for a connection from the pool after 30000ms",
        verified_cause="Unclosed database sessions exhausted the pool",
        resolution_steps=["Fixed session cleanup", "Restarted affected workers"],
        outcome="resolved",
        tags=["demo"],
    )
    retained = await memory.retain_incident(incident)
    print(f"Retain: {'success' if retained.success else retained.error}")
    evidence = await memory.recall_similar("payments API database connection timeout", k=3)
    print(f"Recall: {len(evidence)} result(s)")
    for result in evidence:
        print(f"- {result.raw_text}")
    await memory.close()


if __name__ == "__main__":
    asyncio.run(main())
