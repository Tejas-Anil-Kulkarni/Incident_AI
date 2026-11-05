"""A/B replay of incident sequences with memory disabled and Hindsight enabled."""

import re
import unicodedata
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.root_cause_analyzer import ChatModel, RootCauseAnalyzer
from hindsight_memory.hindsight_client import MemoryStore
from hindsight_memory.models import Incident, ReflectResult, RetainResult


class ReplayStepMetric(BaseModel):
    step: int
    incident_id: str
    prior_incident_count: int
    correct_prior_cause_cited: bool | None
    steps_to_verified_fix: int | None
    matched_verified_cause: str | None
    cited_incident_ids: list[str] = Field(default_factory=list)
    memory_write_success: bool | None = None


class ReplayVariant(BaseModel):
    mode: Literal["memory_disabled", "memory_enabled"]
    steps: list[ReplayStepMetric]
    memory_available: bool


class ReplayLabResult(BaseModel):
    run_id: str
    memory_bank_id: str | None = None
    incidents_replayed: int
    memory_disabled: ReplayVariant
    memory_enabled: ReplayVariant
    notes: list[str] = Field(default_factory=list)


class MemoryDisabled:
    """Explicit memory-off baseline used only by Replay Lab."""

    last_error: None = None

    async def retain_incident(self, incident: Incident) -> RetainResult:
        return RetainResult(success=False, incident_id=incident.id, error="Memory disabled for this replay pass.")

    async def recall_similar(self, query: str, k: int = 5) -> list:
        return []

    async def reflect(self, question: str) -> ReflectResult:
        return ReflectResult(answer="Memory disabled for this replay pass.", raw_text="", success=False)


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_ids: list[str] = Field(min_length=1, max_length=50)

    @field_validator("incident_ids")
    @classmethod
    def ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("incident_ids must be unique")
        return value


class ReplayLab:
    """Run both variants over the same incidents and model, preserving step order."""

    def __init__(self, llm: ChatModel, *, model_name: str, top_k: int = 5) -> None:
        self.llm = llm
        self.model_name = model_name
        self.top_k = top_k

    async def run(
        self,
        incidents: list[Incident],
        memory: MemoryStore,
        *,
        run_id: str | None = None,
        memory_bank_id: str | None = None,
    ) -> ReplayLabResult:
        identifier = run_id or uuid4().hex
        disabled = await self._run_variant(incidents, MemoryDisabled(), enabled=False)
        enabled = await self._run_variant(incidents, memory, enabled=True)
        return ReplayLabResult(
            run_id=identifier,
            memory_bank_id=memory_bank_id,
            incidents_replayed=len(incidents),
            memory_disabled=disabled,
            memory_enabled=enabled,
            notes=[
                "Metrics are computed from recalled IDs and stored verified outcomes.",
                "Steps to verified fix is the first recommendation matching a recorded resolution step.",
                "No aggregate success rate or improvement is inferred from this replay.",
            ],
        )

    async def _run_variant(
        self,
        incidents: list[Incident],
        memory: MemoryStore,
        *,
        enabled: bool,
    ) -> ReplayVariant:
        metrics: list[ReplayStepMetric] = []
        prior: list[Incident] = []
        memory_available = enabled
        for index, incident in enumerate(incidents, start=1):
            # Replay the incident as it appeared before engineer verification.
            current = incident.model_copy(update={
                "suspected_cause": None,
                "verified_cause": None,
                "resolution_steps": [],
                "outcome": "unknown",
                "resolved_at": None,
                "engineer_notes": None,
                "tags": [tag for tag in incident.tags if tag != "engineer_verified"],
            })
            result = await RootCauseAnalyzer(
                memory,
                self.llm,
                model_name=self.model_name,
                top_k=self.top_k,
                use_llm_without_memory=True,
            ).analyze(current)
            if enabled:
                memory_available = memory_available and result.memory_available and not bool(getattr(memory, "last_error", None))
            cited_ids = list(dict.fromkeys(
                cited_id
                for hypothesis in result.analysis.hypotheses
                for cited_id in hypothesis.evidence_incident_ids
            ))
            correct, matched_cause = _correct_citation(incident, prior, cited_ids)
            fix_position = _steps_to_fix(result.analysis.recommended_steps, incident.resolution_steps)
            write_success: bool | None = None
            if enabled:
                replay_incident = incident.model_copy(update={
                    "tags": list(dict.fromkeys([*incident.tags, "replay_lab"])),
                })
                retained = await memory.retain_incident(replay_incident)
                write_success = retained.success
                memory_available = memory_available and retained.success and not bool(getattr(memory, "last_error", None))
            metrics.append(ReplayStepMetric(
                step=index,
                incident_id=incident.id,
                prior_incident_count=len(prior),
                correct_prior_cause_cited=correct,
                steps_to_verified_fix=fix_position,
                matched_verified_cause=matched_cause,
                cited_incident_ids=cited_ids,
                memory_write_success=write_success,
            ))
            prior.append(incident)
        return ReplayVariant(
            mode="memory_enabled" if enabled else "memory_disabled",
            steps=metrics,
            memory_available=memory_available,
        )


def _correct_citation(
    incident: Incident,
    prior: list[Incident],
    cited_ids: list[str],
) -> tuple[bool | None, str | None]:
    if not incident.verified_cause:
        return None, None
    expected = _normalize(incident.verified_cause)
    by_id = {item.id: item for item in prior}
    for incident_id in cited_ids:
        previous = by_id.get(incident_id)
        if previous and previous.verified_cause and _normalize(previous.verified_cause) == expected:
            return True, previous.verified_cause
    return False, None


def _steps_to_fix(recommendations: list[str], verified_steps: list[str]) -> int | None:
    targets = [_tokens(step) for step in verified_steps if step.strip()]
    for index, recommendation in enumerate(recommendations, start=1):
        matched_fix = recommendation.split(": ", 1)[1] if recommendation.startswith("Previously successful in incident ") and ": " in recommendation else recommendation
        candidate = _tokens(matched_fix)
        if any(_similarity(candidate, target) >= 0.6 for target in targets):
            return index
    return None


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w]+", _normalize(value)))


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
