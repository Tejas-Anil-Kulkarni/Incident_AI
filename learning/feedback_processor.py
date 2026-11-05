"""Engineer verification, idempotent feedback recording, and memory updates."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import IncidentRecord
from hindsight_memory.hindsight_client import MemoryStore
from hindsight_memory.models import Incident
from learning.models import FeedbackRecord

logger = logging.getLogger(__name__)


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    verified_cause: str = Field(min_length=1, max_length=10_000)
    suspected_cause: str | None = Field(default=None, min_length=1, max_length=10_000)
    steps_taken: list[str] = Field(default_factory=list, max_length=100)
    outcome: Literal["resolved", "failed", "partial"]
    notes: str = Field(default="", max_length=20_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class FeedbackResponse(BaseModel):
    feedback_id: str
    incident_id: str
    verified_cause: str
    outcome: Literal["resolved", "failed", "partial"]
    memory_retained: bool
    duplicate: bool = False
    warning: str | None = None


class ActionApprovalSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=2_000)
    approved_by: str = Field(min_length=1, max_length=300)


class ActionApprovalResponse(BaseModel):
    incident_id: str
    action_id: str
    action: str
    approved_by: str
    approved_at: datetime
    approved: bool = True


class ActionExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=100)


class ActionSimulationResponse(BaseModel):
    incident_id: str
    action_id: str
    status: Literal["simulated"] = "simulated"
    executed: bool = False
    message: str = "Action was logged for simulation only; no recovery action was executed."


def make_feedback_id(incident_id: str, submission: FeedbackSubmission) -> str:
    identity = submission.idempotency_key or json.dumps(
        submission.model_dump(exclude={"idempotency_key"}), ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(f"{incident_id}\0{identity}".encode("utf-8")).hexdigest()


def verified_incident(incident: Incident, submission: FeedbackSubmission) -> Incident:
    tags = list(dict.fromkeys([*incident.tags, "engineer_verified"]))
    return incident.model_copy(update={
        "verified_cause": submission.verified_cause,
        "suspected_cause": submission.suspected_cause or incident.suspected_cause,
        "resolution_steps": submission.steps_taken,
        "outcome": submission.outcome,
        "engineer_notes": submission.notes or None,
        "tags": tags,
    })


async def record_feedback(
    *,
    db: Session,
    record: IncidentRecord,
    incident: Incident,
    submission: FeedbackSubmission,
    memory: MemoryStore | None,
) -> FeedbackResponse:
    feedback_id = make_feedback_id(incident.id, submission)
    existing = db.get(FeedbackRecord, feedback_id)
    if existing is not None:
        return _response(existing, duplicate=True)

    feedback = FeedbackRecord(
        feedback_id=feedback_id,
        incident_id=incident.id,
        verified_cause=submission.verified_cause,
        outcome=submission.outcome,
        steps_json=json.dumps(submission.steps_taken, ensure_ascii=False),
        notes=submission.notes,
        created_at=datetime.now(timezone.utc),
        memory_retained=False,
    )
    try:
        db.add(feedback)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(FeedbackRecord, feedback_id)
        if existing is not None:
            return _response(existing, duplicate=True)
        raise
    except SQLAlchemyError:
        db.rollback()
        raise

    if memory is not None:
        try:
            retained = await memory.retain_incident(verified_incident(incident, submission))
            feedback.memory_retained = retained.success
            if not retained.success:
                logger.warning("Verified incident feedback was stored but not retained in Hindsight")
        except Exception as exc:
            logger.warning("Verified incident Retain failed: %s", type(exc).__name__)
        db.commit()
    return _response(feedback, duplicate=False)


def _response(record: FeedbackRecord, *, duplicate: bool) -> FeedbackResponse:
    warning = None
    if record.outcome == "failed":
        warning = "This verified outcome was failed; review the recorded steps before recommending them again."
    return FeedbackResponse(
        feedback_id=record.feedback_id,
        incident_id=record.incident_id,
        verified_cause=record.verified_cause,
        outcome=record.outcome,
        memory_retained=record.memory_retained,
        duplicate=duplicate,
        warning=warning,
    )
