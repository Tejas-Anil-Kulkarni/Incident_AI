"""Typed adapter for official Hindsight Reflect responses."""

from hindsight_memory.models import ReflectResult


def adapt_reflect(response: object) -> ReflectResult:
    answer = str(getattr(response, "text", "") or "")
    return ReflectResult(answer=answer, raw_text=answer)
