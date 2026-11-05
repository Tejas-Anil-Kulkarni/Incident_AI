"""Category-to-runbook mapping and evidence-backed successful-fix extraction."""

import json
from pathlib import Path
from typing import Any

from hindsight_memory.models import Incident, MemoryEvidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOKS: dict[str, str] = {
    "Database": "runbooks/database_failure.md",
    "API": "runbooks/api_failure.md",
    "Overload": "runbooks/server_overload.md",
    "Network": "runbooks/network_failure.md",
    "Deployment": "runbooks/deployment_failure.md",
    "Performance": "runbooks/performance_degradation.md",
}


def parse_incident_memory(evidence: MemoryEvidence) -> dict[str, Any] | None:
    """Read IncidentMind's retained JSON payload from Hindsight's raw text."""

    raw = evidence.source_text or evidence.raw_text
    marker = "IncidentMind incident record:\n"
    candidate = raw.split(marker, 1)[1] if marker in raw else raw
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def evidence_incident_id(evidence: MemoryEvidence) -> str | None:
    if evidence.incident_id:
        return evidence.incident_id
    parsed = parse_incident_memory(evidence)
    incident_id = parsed.get("id") if parsed else None
    return str(incident_id) if incident_id else None


def runbook_steps(category: str | None) -> tuple[str, list[str]]:
    """Load human-reviewed steps from the mapped Markdown runbook."""

    ref = RUNBOOKS.get(category or "", RUNBOOKS["API"])
    path = PROJECT_ROOT / ref
    content = path.read_text(encoding="utf-8")
    collecting = False
    steps: list[str] = []
    for line in content.splitlines():
        if line.strip().lower() == "## recommended checks":
            collecting = True
            continue
        if collecting and line.startswith("## "):
            break
        if collecting and line.lstrip().startswith("- "):
            steps.append(line.lstrip()[2:].strip())
    return ref, steps


def successful_resolution_steps(evidence: list[MemoryEvidence]) -> list[str]:
    """Return past resolution steps only from records explicitly marked resolved."""

    suggestions: list[str] = []
    for item in evidence:
        record = parse_incident_memory(item)
        if not record or record.get("outcome") != "resolved":
            continue
        incident_id = str(record.get("id") or evidence_incident_id(item) or "historical")
        for step in record.get("resolution_steps", []):
            if isinstance(step, str) and step.strip():
                suggestions.append(f"Previously successful in incident {incident_id}: {step.strip()}")
    return _unique(suggestions)


def failed_resolution_warnings(evidence: list[MemoryEvidence]) -> list[str]:
    """Surface engineer-recorded failures without treating them as successful fixes."""

    warnings: list[str] = []
    for item in evidence:
        record = parse_incident_memory(item)
        if not record or record.get("outcome") != "failed":
            continue
        incident_id = str(record.get("id") or evidence_incident_id(item) or "historical")
        cause = str(record.get("verified_cause") or record.get("error") or "cause not recorded")
        steps = [step.strip() for step in record.get("resolution_steps", []) if isinstance(step, str) and step.strip()]
        attempted = "; ".join(steps) if steps else "no recovery steps were recorded"
        warnings.append(
            f"Historical warning: incident {incident_id} ended in failure. "
            f"Recorded cause: {cause}. Steps taken: {attempted}. Review before reuse."
        )
    return _unique(warnings)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value.strip()))
