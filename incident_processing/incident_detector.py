"""Convert alert payloads into Phase 1-compatible incident records."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from hindsight_memory.models import Incident
from incident_processing.incident_classifier import classify_incident
from incident_processing.log_analyzer import analyze_logs


class AlertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service: str = Field(min_length=1, max_length=300)
    error: str | None = Field(default=None, max_length=10_000)
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    failed_requests: int = Field(default=0, ge=0)
    status: str = Field(default="unknown", max_length=100)
    logs: str = Field(default="", max_length=200_000)
    occurred_at: datetime | None = None


def detect_incident(alert: AlertPayload | dict[str, object]) -> Incident:
    parsed = alert if isinstance(alert, AlertPayload) else AlertPayload.model_validate(alert)
    log_analysis = analyze_logs(parsed.logs)
    details = " ".join(filter(None, [parsed.error, parsed.status, parsed.logs]))
    classification = classify_incident(
        text=details,
        cpu_percent=parsed.cpu_percent,
        failed_requests=parsed.failed_requests,
        status=parsed.status,
    )
    symptoms = list(log_analysis.repeated_patterns)
    if parsed.cpu_percent is not None:
        symptoms.append(f"CPU utilization {parsed.cpu_percent:g}%")
    if parsed.failed_requests:
        symptoms.append(f"{parsed.failed_requests} failed requests")
    if parsed.status.lower() not in {"unknown", "ok", "healthy", "resolved"}:
        symptoms.append(f"Reported status: {parsed.status}")
    occurred_at = parsed.occurred_at or (log_analysis.timestamps[-1] if log_analysis.timestamps else None)
    return Incident(
        id=str(uuid4()),
        service=parsed.service,
        error=parsed.error or log_analysis.signature or f"Alert reported status {parsed.status}",
        severity=classification.severity,
        symptoms=symptoms,
        top_stack_frames=log_analysis.top_stack_frames,
        logs_excerpt=parsed.logs[:50_000],
        outcome="unknown",
        category=classification.category,
        signature=log_analysis.signature or None,
        occurred_at=occurred_at,
        created_at=datetime.now(timezone.utc),
        tags=[f"category:{classification.category.lower()}", f"signature:{log_analysis.signature[:80]}"] if log_analysis.signature else [f"category:{classification.category.lower()}"],
    )
