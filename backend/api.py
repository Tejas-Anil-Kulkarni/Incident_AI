"""System and incident API routes."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agent.llm_client import GroqChatModel
from agent.root_cause_analyzer import AnalysisResponse, RootCauseAnalyzer, get_root_cause_analyzer
from backend.database import get_db
from backend.models import IncidentRecord
from config.settings import get_feature_flags, get_settings
from hindsight_memory.dependencies import get_memory_store
from hindsight_memory.hindsight_client import HindsightMemory
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
from innovation.replay_lab import ReplayLab, ReplayLabResult, ReplayRequest
from innovation.reflect_insights import ReflectInsightRequest, ReflectInsightResponse, reflect_insight
from innovation.chaos_dojo import ChaosDojoRequest, ChaosDojoResult, generate_synthetic_incident
from innovation.deploy_risk import DeployRiskRequest, DeployRiskResponse, build_deploy_risk_response
from innovation.staleness import StalenessResponse, find_staleness_conflicts

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class IncidentFeedItem(BaseModel):
    incident: Incident
    feedback_outcome: str | None = None
    status: str
    synthetic: bool = False


class MemoryStatsResponse(BaseModel):
    feedback_records: int
    retained_in_hindsight: int


class MemoryOriginStatsResponse(BaseModel):
    real_feedback_records: int
    real_retained_in_hindsight: int
    synthetic_feedback_records: int
    synthetic_retained_in_hindsight: int


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


@router.get("/incidents", response_model=list[IncidentFeedItem], tags=["incidents"])
def list_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[IncidentFeedItem]:
    """Read-only, newest-first incident feed for the dashboard."""

    records = list(db.scalars(
        select(IncidentRecord).order_by(IncidentRecord.created_at.desc()).offset(offset).limit(limit)
    ).all())
    feedback_rows = list(db.scalars(
        select(FeedbackRecord).where(FeedbackRecord.incident_id.in_([item.id for item in records]))
    ).all()) if records else []
    outcomes = {item.incident_id: item.outcome for item in feedback_rows}
    result = []
    for record in records:
        incident = Incident.model_validate_json(record.payload_json)
        outcome = outcomes.get(record.id)
        synthetic = "synthetic=true" in incident.tags
        result.append(IncidentFeedItem(
            incident=incident,
            feedback_outcome=outcome,
            status="synthetic" if synthetic else ("verified" if outcome else "open"),
            synthetic=synthetic,
        ))
    return result


@router.get("/stats/memory", response_model=MemoryStatsResponse, tags=["learning"])
def get_memory_stats(db: Session = Depends(get_db)) -> MemoryStatsResponse:
    """Report locally recorded feedback and confirmed Hindsight retain results."""

    rows = list(db.scalars(select(FeedbackRecord)).all())
    return MemoryStatsResponse(
        feedback_records=len(rows),
        retained_in_hindsight=sum(1 for item in rows if item.memory_retained),
    )


@router.get("/stats/memory/origins", response_model=MemoryOriginStatsResponse, tags=["learning"])
def get_memory_origin_stats(db: Session = Depends(get_db)) -> MemoryOriginStatsResponse:
    """Separate confirmed retains for synthetic examples and real feedback."""

    rows = list(db.scalars(select(FeedbackRecord)).all())
    incident_ids = {row.incident_id for row in rows}
    incident_rows = list(db.scalars(select(IncidentRecord).where(IncidentRecord.id.in_(incident_ids))).all()) if incident_ids else []
    incident_map = {row.id: row for row in incident_rows}
    totals = {"real": [0, 0], "synthetic": [0, 0]}
    for row in rows:
        incident = incident_map.get(row.incident_id)
        is_synthetic = False
        if incident is not None:
            try:
                payload = Incident.model_validate_json(incident.payload_json)
                is_synthetic = "synthetic=true" in payload.tags
            except ValueError:
                pass
        bucket = totals["synthetic" if is_synthetic else "real"]
        bucket[0] += 1
        bucket[1] += int(row.memory_retained)
    return MemoryOriginStatsResponse(
        real_feedback_records=totals["real"][0],
        real_retained_in_hindsight=totals["real"][1],
        synthetic_feedback_records=totals["synthetic"][0],
        synthetic_retained_in_hindsight=totals["synthetic"][1],
    )


@router.post("/incidents/{incident_id}/analyze", response_model=AnalysisResponse, tags=["incidents"])
async def analyze_incident(
    incident_id: str,
    innovation_enabled: bool = False,
    db: Session = Depends(get_db),
    analyzer: RootCauseAnalyzer = Depends(get_root_cause_analyzer),
) -> AnalysisResponse:
    """Return a grounded analysis for a previously ingested incident."""

    record = db.scalar(select(IncidentRecord).where(IncidentRecord.id == incident_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    incident = Incident.model_validate(json.loads(record.payload_json))
    return await analyzer.analyze(incident, innovation_enabled=innovation_enabled)


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
        synthetic = False
        if incident_record is not None:
            try:
                incident = Incident.model_validate_json(incident_record.payload_json)
                category = incident.category
                synthetic = "synthetic=true" in incident.tags
            except ValueError:
                category = None
        entries.append(FeedbackEntry(
            incident_id=item.incident_id,
            category=category,
            verified_cause=item.verified_cause,
            outcome=item.outcome,
            synthetic=synthetic,
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


@router.post("/innovation/replay", response_model=ReplayLabResult, tags=["innovation"])
async def replay_incidents(request: ReplayRequest, db: Session = Depends(get_db)) -> ReplayLabResult:
    """Replay a stored incident sequence in an isolated Hindsight bank."""

    records = list(db.scalars(select(IncidentRecord).where(IncidentRecord.id.in_(request.incident_ids))).all())
    by_id = {item.id: item for item in records}
    missing = [item for item in request.incident_ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Incident not found: {missing[0]}")

    feedback_rows = list(db.scalars(
        select(FeedbackRecord)
        .where(FeedbackRecord.incident_id.in_(request.incident_ids))
        .order_by(FeedbackRecord.created_at.asc())
    ).all())
    feedback_by_incident = {item.incident_id: item for item in feedback_rows}
    sequence: list[Incident] = []
    for incident_id in request.incident_ids:
        incident = Incident.model_validate_json(by_id[incident_id].payload_json)
        feedback = feedback_by_incident.get(incident_id)
        if feedback is not None:
            incident = incident.model_copy(update={
                "verified_cause": feedback.verified_cause,
                "resolution_steps": json.loads(feedback.steps_json),
                "outcome": feedback.outcome,
                "engineer_notes": feedback.notes or None,
            })
        sequence.append(incident)

    try:
        settings = get_settings()
    except ValidationError as exc:
        raise HTTPException(status_code=503, detail="Replay requires configured Hindsight and Groq credentials.") from exc

    run_id = uuid4().hex
    bank_id = f"incidentmind-replay-{run_id[:12]}"
    try:
        memory = await HindsightMemory.connect(settings, bank_id=bank_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Replay Hindsight bank could not be initialized.") from exc
    if memory.last_error:
        await memory.close()
        raise HTTPException(status_code=503, detail="Replay Hindsight bank is unavailable.")
    llm = GroqChatModel(settings.groq_api_key.get_secret_value())
    try:
        return await ReplayLab(llm, model_name=settings.model_name).run(
            sequence,
            memory,
            run_id=run_id,
            memory_bank_id=bank_id,
        )
    finally:
        await memory.close()
        await llm.close()


@router.post("/innovation/insights", response_model=ReflectInsightResponse, tags=["innovation"])
async def get_innovation_insight(
    request: ReflectInsightRequest,
    db: Session = Depends(get_db),
    memory=Depends(get_memory_store),
) -> ReflectInsightResponse:
    """Reflect on retained incidents, caching the result with a local fallback."""

    return await reflect_insight(
        question=request.question,
        db=db,
        memory=memory,
        refresh=request.refresh,
    )


@router.post("/innovation/chaos-dojo", response_model=ChaosDojoResult, tags=["innovation"])
async def run_chaos_dojo(
    request: ChaosDojoRequest,
    db: Session = Depends(get_db),
    memory=Depends(get_memory_store),
    analyzer: RootCauseAnalyzer = Depends(get_root_cause_analyzer),
) -> ChaosDojoResult:
    """Generate, analyze, and retain one explicitly synthetic demonstration."""

    if not get_feature_flags().chaos_dojo_enabled:
        raise HTTPException(status_code=404, detail="Chaos Dojo is disabled.")
    if memory is None:
        raise HTTPException(status_code=503, detail="Chaos Dojo requires an available Hindsight memory service.")
    incident, verified_cause, steps = generate_synthetic_incident(request)
    record = IncidentRecord(
        id=incident.id,
        service=incident.service,
        created_at=incident.created_at,
        signature=incident.signature,
        payload_json=incident.model_dump_json(),
    )
    db.add(record)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Synthetic incident could not be stored.") from exc
    try:
        analysis = await analyzer.analyze(incident)
    except Exception:
        analysis = await RootCauseAnalyzer(memory=None, llm=None).analyze(incident)
    feedback = await record_feedback(
        db=db,
        record=record,
        incident=incident,
        submission=FeedbackSubmission(
            verified_cause=verified_cause,
            steps_taken=steps,
            outcome="resolved",
            notes="Scripted engineer feedback for a synthetic Chaos Dojo scenario.",
        ),
        memory=memory,
    )
    return ChaosDojoResult(
        incident=incident,
        analysis=analysis.model_dump(mode="json"),
        scripted_feedback=feedback.model_dump(mode="json"),
    )


@router.get("/incidents/{incident_id}/staleness", response_model=StalenessResponse, tags=["innovation"])
def get_incident_staleness(
    incident_id: str,
    db: Session = Depends(get_db),
) -> StalenessResponse:
    """Compare verified records for a service and flag older contradictory memories."""

    if not get_feature_flags().staleness_enabled:
        raise HTTPException(status_code=404, detail="Memory staleness detection is disabled.")
    target = db.get(IncidentRecord, incident_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    service_records = list(db.scalars(
        select(IncidentRecord).where(IncidentRecord.service == target.service)
    ).all())
    incident_ids = [item.id for item in service_records]
    feedback_rows = list(db.scalars(
        select(FeedbackRecord).where(FeedbackRecord.incident_id.in_(incident_ids))
    ).all()) if incident_ids else []
    causes = {item.incident_id: item.verified_cause for item in feedback_rows}
    incidents = [Incident.model_validate_json(item.payload_json) for item in service_records]
    result = find_staleness_conflicts(incidents, causes)
    relevant = [
        item for item in result.conflicts
        if item.older_incident_id == incident_id or item.newer_incident_id == incident_id
    ]
    if not relevant:
        return StalenessResponse(conflicts=[], message="No conflicting verified incident memories were found for this incident.")
    return StalenessResponse(conflicts=relevant, message=result.message)


@router.post("/innovation/deploy-risk", response_model=DeployRiskResponse, tags=["innovation"])
async def check_deploy_risk(
    request: DeployRiskRequest,
    memory=Depends(get_memory_store),
) -> DeployRiskResponse:
    """Recall change-related history and return evidence without a risk score."""

    if not get_feature_flags().deploy_risk_enabled:
        raise HTTPException(status_code=404, detail="Deploy risk checks are disabled.")
    if memory is None:
        return build_deploy_risk_response([], available=False, change_description=request.change_description)
    query = " ".join(filter(None, [request.service, "deployment change", request.change_description]))
    try:
        evidence = await memory.recall_similar(query, k=5)
        available = not bool(getattr(memory, "last_error", None))
    except Exception:
        evidence = []
        available = False
    return build_deploy_risk_response(
        evidence,
        available=available,
        change_description=request.change_description,
    )

