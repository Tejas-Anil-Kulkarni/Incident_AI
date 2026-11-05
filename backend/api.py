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
from hindsight_memory.models import Incident
from incident_processing.incident_detector import AlertPayload, detect_incident

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

