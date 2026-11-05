"""Small, clearly synthetic scenarios for exercising the feedback loop."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from hindsight_memory.models import Incident


FaultType = Literal["database_pool", "api_dependency", "worker_overload"]


class ChaosDojoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service: str = Field(default="demo-service", min_length=1, max_length=300)
    fault: FaultType


class ChaosDojoResult(BaseModel):
    synthetic: Literal[True] = True
    incident: Incident
    analysis: dict
    scripted_feedback: dict


SCENARIOS: dict[FaultType, dict] = {
    "database_pool": {
        "category": "Database", "severity": "high",
        "error": "Synthetic fault: database connection pool exhausted",
        "logs": "[SYNTHETIC] Timeout waiting for a database connection from the pool",
        "cause": "Synthetic fault injection exhausted the database pool",
        "steps": ["Restore pool capacity and verify connection cleanup"],
    },
    "api_dependency": {
        "category": "API", "severity": "high",
        "error": "Synthetic fault: upstream dependency requests timed out",
        "logs": "[SYNTHETIC] Upstream request timed out after retry budget",
        "cause": "Synthetic upstream dependency latency exceeded the request budget",
        "steps": ["Check upstream health and configure a bounded timeout"],
    },
    "worker_overload": {
        "category": "Overload", "severity": "critical",
        "error": "Synthetic fault: worker queue saturation",
        "logs": "[SYNTHETIC] Queue depth exceeded worker capacity",
        "cause": "Synthetic load exceeded available worker capacity",
        "steps": ["Inspect queue depth and scale workers within capacity limits"],
    },
}


def generate_synthetic_incident(request: ChaosDojoRequest) -> tuple[Incident, str, list[str]]:
    scenario = SCENARIOS[request.fault]
    incident = Incident(
        id=f"synthetic-{uuid4().hex}",
        service=request.service,
        error=scenario["error"],
        severity=scenario["severity"],
        symptoms=[scenario["error"]],
        logs_excerpt=scenario["logs"],
        category=scenario["category"],
        signature=f"synthetic:{request.fault}",
        created_at=datetime.now(timezone.utc),
        tags=["synthetic=true", "chaos_dojo", f"fault:{request.fault}"],
    )
    return incident, scenario["cause"], list(scenario["steps"])
