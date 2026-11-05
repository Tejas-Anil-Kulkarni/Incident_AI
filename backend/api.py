"""System and incident API routes."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agent.root_cause_analyzer import AnalysisResponse, RootCauseAnalyzer, get_root_cause_analyzer
from backend.database import get_db
from backend.models import IncidentRecord
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.models import Incident
from incident_processing.incident_detector import AlertPayload, detect_incident
from learning.feedback_processor import (
    ActionApprovalResponse,
    ActionApprovalSubmission,
    ActionExecutionRequest,
    ActionSimulationResponse,
    FeedbackResponse,
    FeedbackSubmission,
    record_feedback,
)
from learning.models import ActionApproval, ActionSimulation, FeedbackRecord
from learning.outcome_stats import FeedbackEntry, OutcomeStatsResponse, compute_outcome_stats

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, status_code=200, tags=["system"])
def health() -> HealthResponse:
    """Liveness check. This contract remains stable across all phases."""

    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


@router.post("/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED, tags=["incidents"])
def create_incident(alert: AlertPayload, db: Session = Depends(get_db)) -> Incident:
    """Parse an alert, classify it, and persist the structured incident."""

    incident = detect_incident(alert)
    record = IncidentRecord(
        id=incident.id,
        service=incident.service,
        created_at=incident.created_at,
        signature=incident.signature,
        payload_json=incident.model_dump_json(),
    )
    try:
        db.add(record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Incident storage is temporarily unavailable.") from exc
    return incident


@router.get("/incidents/{incident_id}", response_model=Incident, tags=["incidents"])
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    """Return a persisted structured incident by its generated ID."""

    record = db.scalar(select(IncidentRecord).where(IncidentRecord.id == incident_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return Incident.model_validate(json.loads(record.payload_json))


@router.post("/incidents/{incident_id}/analyze", response_model=AnalysisResponse, tags=["incidents"])
async def analyze_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    analyzer: RootCauseAnalyzer = Depends(get_root_cause_analyzer),
) -> AnalysisResponse:
    """Return a grounded analysis for a previously ingested incident."""

    record = db.scalar(select(IncidentRecord).where(IncidentRecord.id == incident_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    incident = Incident.model_validate(json.loads(record.payload_json))
    return await analyzer.analyze(incident)


@router.post("/incidents/{incident_id}/feedback", response_model=FeedbackResponse, tags=["incidents"])
async def submit_incident_feedback(
    incident_id: str,
    feedback: FeedbackSubmission,
    db: Session = Depends(get_db),
    memory=Depends(get_memory_store),
) -> FeedbackResponse:
    """Store engineer verification once and retain it in Hindsight when available."""

    record = db.scalar(select(IncidentRecord).where(IncidentRecord.id == incident_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    incident = Incident.model_validate(json.loads(record.payload_json))
    try:
        return await record_feedback(db=db, record=record, incident=incident, submission=feedback, memory=memory)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Feedback storage is temporarily unavailable.") from exc


@router.get("/stats/outcomes", response_model=OutcomeStatsResponse, tags=["learning"])
def get_outcome_stats(db: Session = Depends(get_db)) -> OutcomeStatsResponse:
    """Return computed outcome counts from persisted engineer feedback."""

    feedback_rows = list(db.scalars(select(FeedbackRecord)).all())
    incident_ids = {item.incident_id for item in feedback_rows}
    incident_rows = list(db.scalars(select(IncidentRecord).where(IncidentRecord.id.in_(incident_ids))).all()) if incident_ids else []
    incidents_by_id = {item.id: item for item in incident_rows}
    entries: list[FeedbackEntry] = []
    for item in feedback_rows:
        incident_record = incidents_by_id.get(item.incident_id)
        category = None
        if incident_record is not None:
            try:
                category = Incident.model_validate_json(incident_record.payload_json).category
            except ValueError:
                category = None
        entries.append(FeedbackEntry(
            incident_id=item.incident_id,
            category=category,
            verified_cause=item.verified_cause,
            outcome=item.outcome,
        ))
    return compute_outcome_stats(entries)


@router.post("/incidents/{incident_id}/approve-action", response_model=ActionApprovalResponse, tags=["safety"])
def approve_action(
    incident_id: str,
    approval: ActionApprovalSubmission,
    db: Session = Depends(get_db),
) -> ActionApprovalResponse:
    """Record explicit engineer approval for one exact proposed action."""

    if db.get(IncidentRecord, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    approved_at = datetime.now(timezone.utc)
    existing = db.get(ActionApproval, (incident_id, approval.action_id))
    if existing is None:
        existing = ActionApproval(incident_id=incident_id, action_id=approval.action_id)
        db.add(existing)
    existing.action = approval.action
    existing.approved_by = approval.approved_by
    existing.approved_at = approved_at
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Approval record could not be saved.") from exc
    return ActionApprovalResponse(
        incident_id=incident_id,
        action_id=approval.action_id,
        action=approval.action,
        approved_by=approval.approved_by,
        approved_at=approved_at,
    )


@router.post("/incidents/{incident_id}/execute-action", response_model=ActionSimulationResponse, tags=["safety"])
def simulate_approved_action(
    incident_id: str,
    request: ActionExecutionRequest,
    db: Session = Depends(get_db),
) -> ActionSimulationResponse:
    """Log an approved action as a simulation; never execute a recovery command."""

    if db.get(IncidentRecord, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    approval = db.get(ActionApproval, (incident_id, request.action_id))
    if approval is None:
        raise HTTPException(status_code=409, detail="Engineer approval is required before action simulation.")
    db.add(ActionSimulation(
        incident_id=incident_id,
        action_id=request.action_id,
        action=approval.action,
        simulated_at=datetime.now(timezone.utc),
        status="simulated",
    ))
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Action simulation could not be logged.") from exc
    return ActionSimulationResponse(incident_id=incident_id, action_id=request.action_id)

