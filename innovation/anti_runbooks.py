"""Warnings built only from engineer-recorded failed or partial recovery attempts."""

import re
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from agent.runbook_recommender import evidence_incident_id, parse_incident_memory
from hindsight_memory.models import MemoryEvidence


class AntiRunbookWarning(BaseModel):
    attempted_step: str
    failed_count: int
    attempted_count: int
    failed_incident_ids: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    message: str


def build_anti_runbook_warnings(evidence: list[MemoryEvidence]) -> list[AntiRunbookWarning]:
    """Aggregate matching steps across distinct incidents; warn only with failures."""

    records_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        record = parse_incident_memory(item)
        if not record or record.get("outcome") not in {"resolved", "failed", "partial"}:
            continue
        incident_id = str(record.get("id") or evidence_incident_id(item) or "")
        if incident_id:
            records_by_id.setdefault(incident_id, record)

    attempts: dict[str, dict[str, Any]] = defaultdict(lambda: {"step": "", "records": []})
    for incident_id, record in records_by_id.items():
        steps = record.get("resolution_steps", [])
        if not isinstance(steps, list):
            continue
        unique_steps = {step.strip() for step in steps if isinstance(step, str) and step.strip()}
        for step in unique_steps:
            key = _normalize(step)
            attempts[key]["step"] = step.strip()
            attempts[key]["records"].append((incident_id, record))

    warnings: list[AntiRunbookWarning] = []
    for grouped in attempts.values():
        observed = grouped["records"]
        failed = [(incident_id, record) for incident_id, record in observed if record.get("outcome") == "failed"]
        if not failed:
            continue
        failed_ids = sorted({incident_id for incident_id, _ in failed})
        contexts: list[str] = []
        for incident_id, record in failed:
            cause = record.get("verified_cause") or record.get("error") or "cause not recorded"
            notes = record.get("engineer_notes")
            suffix = f" Engineer notes: {notes}" if notes else ""
            contexts.append(f"Incident {incident_id}: {cause}.{suffix}")
        count_failed = len(failed_ids)
        count_attempted = len({incident_id for incident_id, _ in observed})
        step = grouped["step"]
        message = (
            f"Tried before and failed in {count_failed} of {count_attempted} recorded cases "
            f"(incident IDs: {', '.join(failed_ids)}): {step}. Review the failure context before reuse."
        )
        warnings.append(AntiRunbookWarning(
            attempted_step=step,
            failed_count=count_failed,
            attempted_count=count_attempted,
            failed_incident_ids=failed_ids,
            context=contexts,
            message=message,
        ))
    return sorted(warnings, key=lambda item: (item.attempted_step.casefold(), item.failed_incident_ids))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
