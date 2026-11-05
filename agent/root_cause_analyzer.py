"""Evidence-grounded root cause hypotheses and safe recommendations."""

import json
import logging
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.llm_client import GroqChatModel
from agent.runbook_recommender import (
    evidence_incident_id,
    failed_resolution_warnings,
    runbook_steps,
    successful_resolution_steps,
)
from config.settings import get_settings
from hindsight_memory.hindsight_client import HindsightMemory, MemoryStore
from hindsight_memory.models import Incident, MemoryEvidence
from innovation.anti_runbooks import AntiRunbookWarning, build_anti_runbook_warnings

logger = logging.getLogger(__name__)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str = Field(min_length=1)
    evidence_incident_ids: list[str] = Field(...)
    reasoning: str = Field(min_length=1)
    status: Literal["suspected"]


class AnalysisDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[Hypothesis] = Field(...)
    recommended_steps: list[str] = Field(...)
    runbook_ref: str = Field(min_length=1)


class AnalysisResponse(BaseModel):
    incident_id: str
    analysis: AnalysisDraft
    evidence: list[MemoryEvidence] = Field(default_factory=list)
    cold_start: bool
    memory_available: bool
    used_fallback: bool
    warnings: list[str] = Field(default_factory=list)
    anti_runbook_warnings: list[AntiRunbookWarning] = Field(default_factory=list)
    message: str


class ChatModel(Protocol):
    async def complete_json(self, *, model: str, messages: list[dict[str, str]]) -> str: ...


SYSTEM_PROMPT = """You are IncidentMind, an incident-response assistant.
Use only the current incident and the supplied recalled memory evidence.
Historical incident IDs may only be cited when present in the evidence list.
Do not invent historical incidents, outcomes, confidence scores, or evidence.
Label every cause as suspected; only an engineer may verify a cause.
Recommend recovery steps for engineer review. Never claim that an action was run.
Return a JSON object with hypotheses, recommended_steps, and runbook_ref.
Each hypothesis must contain cause, evidence_incident_ids, reasoning, and status='suspected'."""


class RootCauseAnalyzer:
    def __init__(
        self,
        memory: MemoryStore | None,
        llm: ChatModel | None,
        *,
        model_name: str = "openai/gpt-oss-120b",
        top_k: int = 5,
        use_llm_without_memory: bool = False,
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.model_name = model_name
        self.top_k = max(1, min(10, top_k))
        self.use_llm_without_memory = use_llm_without_memory

    async def analyze(self, incident: Incident, *, innovation_enabled: bool = False) -> AnalysisResponse:
        runbook_ref, safe_steps = runbook_steps(incident.category)
        evidence: list[MemoryEvidence] = []
        memory_error = self.memory is None
        if self.memory is not None:
            query = " ".join(filter(None, [incident.service, incident.category, incident.error, *incident.symptoms]))
            evidence = await self.memory.recall_similar(query, k=self.top_k)
            memory_error = bool(getattr(self.memory, "last_error", None))
            evidence = [
                item.model_copy(update={"incident_id": evidence_incident_id(item)})
                if item.incident_id is None and evidence_incident_id(item)
                else item
                for item in evidence
            ]
        historical_warnings = failed_resolution_warnings(evidence)
        anti_runbooks = build_anti_runbook_warnings(evidence) if innovation_enabled else []
        if innovation_enabled:
            historical_warnings.extend(item.message for item in anti_runbooks)

        if (not evidence and (not self.use_llm_without_memory or memory_error)) or memory_error or self.llm is None:
            available = self.memory is not None and not memory_error
            if not available:
                message = "Hindsight memory is unavailable; no historical evidence is being claimed."
            elif not evidence:
                message = "No relevant experience found in memory. Recommendations are based on the runbook only."
            else:
                message = "AI analysis is unavailable. Recommendations are based on the runbook only."
            return AnalysisResponse(
                incident_id=incident.id,
                analysis=AnalysisDraft(hypotheses=[], recommended_steps=safe_steps, runbook_ref=runbook_ref),
                evidence=evidence,
                cold_start=not evidence,
                memory_available=available,
                used_fallback=True,
                warnings=historical_warnings,
                anti_runbook_warnings=anti_runbooks,
                message=message,
            )

        draft = await self._generate(incident, evidence)
        if draft is None:
            return AnalysisResponse(
                incident_id=incident.id,
                analysis=AnalysisDraft(hypotheses=[], recommended_steps=safe_steps, runbook_ref=runbook_ref),
                evidence=evidence,
                cold_start=False,
                memory_available=True,
                used_fallback=True,
                warnings=historical_warnings,
                anti_runbook_warnings=anti_runbooks,
                message="AI analysis failed validation or was unavailable. Recommendations are based on the runbook only.",
            )

        warnings: list[str] = list(historical_warnings)
        allowed_ids = {item.incident_id for item in evidence if item.incident_id}
        hypotheses: list[Hypothesis] = []
        for hypothesis in draft.hypotheses:
            invalid = set(hypothesis.evidence_incident_ids) - allowed_ids
            if invalid:
                warnings.append("Unrecalled incident IDs were removed from the analysis.")
            hypotheses.append(
                hypothesis.model_copy(update={
                    "evidence_incident_ids": [item for item in hypothesis.evidence_incident_ids if item in allowed_ids],
                    "status": "suspected",
                })
            )
        recommendations = list(dict.fromkeys(
            successful_resolution_steps(evidence)
            + [step.strip() for step in draft.recommended_steps if step.strip()]
            + safe_steps
        ))
        return AnalysisResponse(
            incident_id=incident.id,
            analysis=AnalysisDraft(hypotheses=hypotheses, recommended_steps=recommendations, runbook_ref=runbook_ref),
            evidence=evidence,
            cold_start=not evidence,
            memory_available=True,
            used_fallback=False,
            warnings=warnings,
            anti_runbook_warnings=anti_runbooks,
            message=(
                "No relevant experience found in memory. Analysis used the current incident only; "
                "no historical claims were accepted."
                if not evidence
                else "Analysis uses recalled incident evidence; all causes remain suspected until engineer verification."
            ),
        )

    async def _generate(self, incident: Incident, evidence: list[MemoryEvidence]) -> AnalysisDraft | None:
        if self.llm is None:
            return None
        current = incident.model_dump(mode="json")
        current["logs_excerpt"] = incident.logs_excerpt[:6_000]
        histories = [
            {
                "incident_id": item.incident_id,
                "raw_memory": item.raw_text[:4_000],
                "source_chunk": item.source_text[:6_000] if item.source_text else None,
            }
            for item in evidence
        ]
        user_text = json.dumps({"current_incident": current, "recalled_evidence": histories}, ensure_ascii=False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        try:
            raw = await self.llm.complete_json(model=self.model_name, messages=messages)
            return AnalysisDraft.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError) as first_error:
            # Invalid JSON/schema or a stray tool-call payload gets one explicit repair attempt.
            repair_messages = messages + [
                {"role": "assistant", "content": str(raw)[:6000] if "raw" in locals() else ""},
                {"role": "user", "content": (
                    "Repair your previous response. Return only a JSON object valid for this schema: "
                    f"{AnalysisDraft.model_json_schema()}. Validation issue: {str(first_error)[:1500]}"
                )},
            ]
            try:
                repaired = await self.llm.complete_json(model=self.model_name, messages=repair_messages)
                return AnalysisDraft.model_validate_json(repaired)
            except Exception as exc:
                logger.warning("Groq response repair failed: %s", type(exc).__name__)
                return None
        except Exception as exc:
            logger.warning("Root cause LLM analysis failed: %s", type(exc).__name__)
            return None


async def get_root_cause_analyzer():
    """Create request-scoped integrations; keep the route available without secrets."""

    try:
        settings = get_settings()
    except ValidationError:
        yield RootCauseAnalyzer(memory=None, llm=None)
        return

    memory: HindsightMemory | None = None
    llm: GroqChatModel | None = None
    try:
        memory = await HindsightMemory.connect(settings, bank_id=settings.hindsight_bank_id)
    except Exception as exc:
        logger.warning("Hindsight setup unavailable for analysis: %s", type(exc).__name__)
    try:
        llm = GroqChatModel(settings.groq_api_key.get_secret_value())
    except Exception as exc:
        logger.warning("Groq setup unavailable for analysis: %s", type(exc).__name__)
    try:
        yield RootCauseAnalyzer(memory=memory, llm=llm, model_name=settings.model_name)
    finally:
        if memory is not None:
            await memory.close()
        if llm is not None:
            await llm.close()
