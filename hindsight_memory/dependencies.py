"""Request-scoped Hindsight dependency with a graceful unavailable mode."""

import logging
from collections.abc import AsyncIterator

from pydantic import ValidationError

from config.settings import get_settings
from hindsight_memory.hindsight_client import HindsightMemory, MemoryStore

logger = logging.getLogger(__name__)


async def get_memory_store() -> AsyncIterator[MemoryStore | None]:
    try:
        settings = get_settings()
    except ValidationError:
        yield None
        return
    try:
        memory = await HindsightMemory.connect(settings, bank_id=settings.hindsight_bank_id)
    except Exception as exc:
        logger.warning("Hindsight setup unavailable: %s", type(exc).__name__)
        yield None
        return
    try:
        yield memory
    finally:
        await memory.close()
