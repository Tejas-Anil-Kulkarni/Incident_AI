"""Typed adapter for official Hindsight Recall responses."""

from typing import Any

from hindsight_memory.models import MemoryEvidence


def adapt_recall(response: Any, limit: int) -> list[MemoryEvidence]:
    """Adapt documented RecallResponse.results without changing the evidence text."""

    results = getattr(response, "results", None) or []
    chunks = getattr(response, "chunks", None) or {}
    evidence: list[MemoryEvidence] = []
    for item in results[:limit]:
        text = str(getattr(item, "text", "") or "")
        if not text:
            continue
        chunk_id = getattr(item, "chunk_id", None)
        chunk = chunks.get(chunk_id) if chunk_id else None
        source_text = getattr(chunk, "text", None) if chunk else None
        evidence.append(
            MemoryEvidence(
                text=text,
                raw_text=text,
                source_text=str(source_text) if source_text else None,
                memory_id=_optional_str(getattr(item, "id", None)),
                relevance=_optional_float(getattr(item, "relevance", getattr(item, "score", None))),
            )
        )
    return evidence


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
