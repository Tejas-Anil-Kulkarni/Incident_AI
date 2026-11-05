"""Deterministic in-memory test double. Never selected by production factories."""

import re
from collections.abc import Iterable

from hindsight_memory.memory_retain import incident_content
from hindsight_memory.models import Incident, MemoryEvidence, ReflectResult, RetainResult


class FakeMemory:
    """Test implementation with the same async contract as HindsightMemory."""

    def __init__(self, incidents: Iterable[Incident] = ()) -> None:
        self._records: dict[str, Incident] = {item.id: item for item in incidents}

    async def retain_incident(self, incident: Incident) -> RetainResult:
        self._records[incident.id] = incident
        return RetainResult(success=True, incident_id=incident.id)

    async def recall_similar(self, query: str, k: int = 5) -> list[MemoryEvidence]:
        terms = _terms(query)
        if not terms or k <= 0:
            return []
        ranked: list[tuple[int, Incident]] = []
        for incident in self._records.values():
            content = incident_content(incident)
            score = len(terms & _terms(content))
            if score:
                ranked.append((score, incident))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [
            MemoryEvidence(
                text=incident_content(item),
                raw_text=incident_content(item),
                incident_id=item.id,
                relevance=score / len(terms),
            )
            for score, item in ranked[:k]
        ]

    async def reflect(self, question: str) -> ReflectResult:
        evidence = await self.recall_similar(question, k=5)
        if not evidence:
            return ReflectResult(answer="No relevant incident memories found.", raw_text="")
        texts = "\n".join(item.raw_text for item in evidence)
        return ReflectResult(answer=texts, raw_text=texts)


def _terms(value: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[\w-]+", value) if len(word) > 2}
