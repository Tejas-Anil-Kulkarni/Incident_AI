"""Retain the bundled sample incident records in the configured Hindsight bank."""

import asyncio
import json
from pathlib import Path

from config.settings import get_settings
from hindsight_memory.hindsight_client import HindsightMemory
from hindsight_memory.models import Incident


async def seed() -> None:
    records_path = Path(__file__).resolve().parents[1] / "data" / "sample_incidents.json"
    records = [Incident.model_validate(item) for item in json.loads(records_path.read_text(encoding="utf-8"))]
    memory = await HindsightMemory.connect(get_settings())
    for incident in records:
        result = await memory.retain_incident(incident)
        print(f"{incident.id}: {'retained' if result.success else result.error}")
    await memory.close()


if __name__ == "__main__":
    asyncio.run(seed())
