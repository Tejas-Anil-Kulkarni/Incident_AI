"""Evidence-only deploy risk lookup; it does not invent a probability or score."""

from pydantic import BaseModel, ConfigDict, Field

from agent.runbook_recommender import evidence_incident_id, parse_incident_memory
from hindsight_memory.models import MemoryEvidence


class DeployRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    change_description: str = Field(min_length=5, max_length=5_000)
    service: str | None = Field(default=None, max_length=300)


class DeployEvidence(BaseModel):
    incident_id: str | None = None
    service: str | None = None
    verified_cause: str | None = None
    outcome: str | None = None
    text: str
    relevance: float | None = None


class DeployRiskResponse(BaseModel):
    available: bool
    historical_evidence: list[DeployEvidence] = Field(default_factory=list)
    synthetic_evidence: list[DeployEvidence] = Field(default_factory=list)
    message: str


def build_deploy_risk_response(
    evidence: list[MemoryEvidence], *, available: bool, change_description: str
) -> DeployRiskResponse:
    historical: list[DeployEvidence] = []
    synthetic: list[DeployEvidence] = []
    for item in evidence:
        parsed = parse_incident_memory(item) or {}
        entry = DeployEvidence(
            incident_id=evidence_incident_id(item),
            service=parsed.get("service"),
            verified_cause=parsed.get("verified_cause"),
            outcome=parsed.get("outcome"),
            text=item.source_text or item.raw_text,
            relevance=item.relevance,
        )
        tags = parsed.get("tags") if isinstance(parsed.get("tags"), list) else []
        (synthetic if "synthetic=true" in tags else historical).append(entry)
    if not available:
        message = "Hindsight is unavailable; no historical deployment evidence was retrieved."
    elif not historical and not synthetic:
        message = "No related historical incidents were recalled for this change description."
    else:
        message = (
            f"Retrieved {len(historical)} historical and {len(synthetic)} synthetic evidence item(s) "
            "for engineer review. This is not a probability or deployment decision."
        )
    return DeployRiskResponse(
        available=available,
        historical_evidence=historical,
        synthetic_evidence=synthetic,
        message=message,
    )
