"""Typed IncidentMind payloads exchanged with the Hindsight memory layer."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Incident(BaseModel):
    """Validated incident record retained as a Hindsight memory."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=300)
    error: str = Field(min_length=1, max_length=10_000)
    severity: Literal["critical", "high", "medium", "low", "unknown"] = "unknown"
    symptoms: list[str] = Field(default_factory=list)
    top_stack_frames: list[str] = Field(default_factory=list)
    logs_excerpt: str = Field(default="", max_length=50_000)
    suspected_cause: str | None = None
    verified_cause: str | None = None
    engineer_notes: str | None = Field(default=None, max_length=20_000)
    resolution_steps: list[str] = Field(default_factory=list)
    outcome: Literal["resolved", "failed", "partial", "unknown"] = "unknown"
    category: Literal["Database", "API", "Overload", "Network", "Deployment", "Performance"] | None = None
    signature: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class RetainResult(BaseModel):
    success: bool
    incident_id: str
    error: str | None = None


class MemoryEvidence(BaseModel):
    text: str
    raw_text: str
    source_text: str | None = None
    memory_id: str | None = None
    relevance: float | None = None
    incident_id: str | None = None


class ReflectResult(BaseModel):
    answer: str
    raw_text: str
    success: bool = True
    error: str | None = None
