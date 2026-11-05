"""Thin async application adapter over Vectorize's official Hindsight SDK."""

import asyncio
import logging
import random
import uuid
from typing import Any, Protocol

from hindsight_memory.memory_recall import adapt_recall
from hindsight_memory.memory_reflect import adapt_reflect
from hindsight_memory.memory_retain import incident_content
from hindsight_memory.models import Incident, MemoryEvidence, ReflectResult, RetainResult

logger = logging.getLogger(__name__)


class MemoryStore(Protocol):
    async def retain_incident(self, incident: Incident) -> RetainResult: ...
    async def recall_similar(self, query: str, k: int = 5) -> list[MemoryEvidence]: ...
    async def reflect(self, question: str) -> ReflectResult: ...


class HindsightMemory:
    """Calls only documented Hindsight SDK operations; never substitutes a fake."""

    BANK_ID = "incidentmind"

    def __init__(self, client: Any, *, retries: int = 2, backoff_seconds: float = 0.25, bank_ready: bool = True) -> None:
        self._client = client
        self._retries = max(0, retries)
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._bank_ready = bank_ready
        self.last_error: str | None = None

    @classmethod
    async def connect(cls, settings: Any, *, retries: int = 2, backoff_seconds: float = 0.25) -> "HindsightMemory":
        """Create/retrieve the stable bank using Hindsight's create-or-update API."""

        from hindsight_client import Hindsight

        client = Hindsight(
            base_url=str(settings.hindsight_base_url),
            api_key=settings.hindsight_api_key.get_secret_value(),
            timeout=10.0,
        )
        instance = cls(client, retries=retries, backoff_seconds=backoff_seconds, bank_ready=False)
        try:
            await instance._ensure_bank()
        except Exception as exc:
            # Keep the application available during an outage; each operation
            # retries bank initialization and then uses its normal fallback.
            logger.warning("Hindsight bank initialization failed: %s", type(exc).__name__)
            instance.last_error = "hindsight_unavailable"
        return instance

    async def retain_incident(self, incident: Incident) -> RetainResult:
        content = incident_content(incident)
        try:
            await self._ensure_bank()
            response = await self._call(lambda: self._client.retain(
                bank_id=self.BANK_ID,
                content=content,
                context=f"Incident {incident.id} for service {incident.service}",
                document_id=f"incident-{incident.id}",
                metadata={"incidentmind_id": incident.id, "outcome": incident.outcome},
                tags=incident.tags,
                retain_async=True,
                operation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"incidentmind:{incident.id}")),
            ))
            if getattr(response, "success", True) is False:
                raise RuntimeError("Hindsight rejected the Retain request")
            self.last_error = None
            return RetainResult(success=True, incident_id=incident.id)
        except Exception as exc:
            self.last_error = "hindsight_unavailable"
            logger.warning("Hindsight Retain failed for incident %s: %s", incident.id, type(exc).__name__)
            return RetainResult(success=False, incident_id=incident.id, error="Hindsight memory is temporarily unavailable.")

    async def recall_similar(self, query: str, k: int = 5) -> list[MemoryEvidence]:
        if not query.strip() or k <= 0:
            return []
        try:
            await self._ensure_bank()
            response = await self._call(lambda: self._client.recall(
                bank_id=self.BANK_ID,
                query=query,
                max_tokens=max(256, min(8192, k * 1200)),
                include_chunks=True,
                max_chunk_tokens=1200,
            ))
            self.last_error = None
            return adapt_recall(response, k)
        except Exception as exc:
            self.last_error = "hindsight_unavailable"
            logger.warning("Hindsight Recall failed: %s", type(exc).__name__)
            return []

    async def reflect(self, question: str) -> ReflectResult:
        try:
            await self._ensure_bank()
            response = await self._call(lambda: self._client.reflect(bank_id=self.BANK_ID, query=question))
            self.last_error = None
            return adapt_reflect(response)
        except Exception as exc:
            self.last_error = "hindsight_unavailable"
            logger.warning("Hindsight Reflect failed: %s", type(exc).__name__)
            return ReflectResult(
                answer="Hindsight reflection is temporarily unavailable.",
                raw_text="",
                success=False,
                error="Hindsight memory is temporarily unavailable.",
            )

    async def _ensure_bank(self) -> None:
        if self._bank_ready:
            return
        await self._call(lambda: self._client.create_bank(
            bank_id=self.BANK_ID,
            name="IncidentMind",
            reflect_mission="Analyze verified and suspected incident history. Distinguish evidence from hypotheses.",
        ))
        self._bank_ready = True

    async def _call(self, operation: Any) -> Any:
        for attempt in range(self._retries + 1):
            try:
                return await asyncio.wait_for(asyncio.to_thread(operation), timeout=12.0)
            except Exception:
                if attempt >= self._retries:
                    raise
                delay = self._backoff_seconds * (2**attempt) * random.uniform(0.8, 1.2)
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable retry state")

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await asyncio.to_thread(close)
