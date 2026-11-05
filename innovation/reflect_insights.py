"""Hindsight Reflect queries with timestamped SQLite cache and honest fallback."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import IncidentRecord
from hindsight_memory.hindsight_client import MemoryStore
from learning.models import FeedbackRecord
from innovation.models import ReflectInsightCache

CACHE_TTL_SECONDS = 300


class ReflectInsightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=2_000)
    refresh: bool = False


class ReflectInsightResponse(BaseModel):
    question: str
    answer: str
    raw_text: str
    source: Literal["hindsight", "sqlite_fallback"]
    cached: bool
    cached_at: datetime
    success: bool


async def reflect_insight(
    *,
    question: str,
    db: Session,
    memory: MemoryStore | None,
    refresh: bool = False,
    now: datetime | None = None,
) -> ReflectInsightResponse:
    current = now or datetime.now(timezone.utc)
    key = _cache_key(question)
    cached = db.get(ReflectInsightCache, key)
    if cached is not None and not refresh:
        created_at = _aware(cached.created_at)
        if current - created_at < timedelta(seconds=CACHE_TTL_SECONDS):
            return ReflectInsightResponse(
                question=question,
                answer=cached.answer,
                raw_text=cached.raw_text,
                source=cached.source,
                cached=True,
                cached_at=created_at,
                success=cached.success,
            )

    reflected = None
    if memory is not None:
        try:
            reflected = await memory.reflect(question)
        except Exception:
            reflected = None
    if reflected is not None and reflected.success and reflected.answer.strip():
        answer = reflected.answer
        raw_text = reflected.raw_text
        source: Literal["hindsight", "sqlite_fallback"] = "hindsight"
        success = True
    else:
        answer = local_feedback_reflection(question, db)
        raw_text = answer
        source = "sqlite_fallback"
        success = False

    record = ReflectInsightCache(
        cache_key=key,
        question=question,
        answer=answer,
        raw_text=raw_text,
        source=source,
        success=success,
        created_at=current,
    )
    db.merge(record)
    db.commit()
    return ReflectInsightResponse(
        question=question,
        answer=answer,
        raw_text=raw_text,
        source=source,
        cached=False,
        cached_at=current,
        success=success,
    )


def local_feedback_reflection(question: str, db: Session) -> str:
    """Compute a grounded fallback summary from engineer-submitted records only."""

    entries = list(db.scalars(select(FeedbackRecord).order_by(FeedbackRecord.created_at.asc())).all())
    if not entries:
        return "No engineer feedback has been recorded in SQLite."
    incident_ids = {entry.incident_id for entry in entries}
    incidents = list(db.scalars(select(IncidentRecord).where(IncidentRecord.id.in_(incident_ids))).all())
    incident_by_id = {item.id: item for item in incidents}
    lower = question.casefold()
    if "failed" in lower or "failure" in lower:
        failed = [item for item in entries if item.outcome == "failed"]
        if not failed:
            return "No failed fixes are present in recorded engineer feedback."
        lines = ["Failed fixes from recorded engineer feedback:"]
        for item in failed:
            steps = "; ".join(json.loads(item.steps_json)) or "no steps recorded"
            lines.append(
                f"- Incident {item.incident_id}: {item.verified_cause}; steps: {steps}; notes: {item.notes or 'none recorded'}."
            )
        return "\n".join(lines)

    category_by_id = {item.id: _category(item.payload_json) for item in incidents}
    if "cause" in lower or "service" in lower:
        grouped: dict[tuple[str, str], int] = defaultdict(int)
        for item in entries:
            incident = incident_by_id.get(item.incident_id)
            service = incident.service if incident else "unknown service"
            grouped[(service, item.verified_cause)] += 1
        lines = [
            f"{service}: {cause} ({count} recorded)"
            for (service, cause), count in sorted(grouped.items(), key=lambda pair: (-pair[1], pair[0]))
        ]
        return "Verified causes by service, from engineer feedback:\n" + "\n".join(f"- {line}" for line in lines)

    if "recurring" in lower or "infrastructure" in lower:
        grouped: Counter[tuple[str, str | None]] = Counter()
        for item in entries:
            incident = incident_by_id.get(item.incident_id)
            service = incident.service if incident else "unknown service"
            grouped[(service, category_by_id.get(item.incident_id))] += 1
        lines = [
            f"{service}: {category or 'Unknown'} ({count} recorded)"
            for (service, category), count in sorted(
                grouped.items(), key=lambda pair: (-pair[1], (pair[0][0], pair[0][1] or ""))
            )
        ]
        return "Recurring categories in recorded engineer feedback:\n" + "\n".join(f"- {line}" for line in lines)

    counts = Counter(item.outcome for item in entries)
    return (
        f"Recorded engineer feedback: {len(entries)} total; "
        f"{counts.get('resolved', 0)} resolved, {counts.get('failed', 0)} failed, "
        f"{counts.get('partial', 0)} partial."
    )


def _cache_key(question: str) -> str:
    return hashlib.sha256(question.strip().casefold().encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _category(payload_json: str) -> str | None:
    try:
        return json.loads(payload_json).get("category")
    except (ValueError, AttributeError):
        return None
