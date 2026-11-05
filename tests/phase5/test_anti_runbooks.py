import json

import pytest

from agent.root_cause_analyzer import RootCauseAnalyzer
from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.memory_retain import incident_content
from hindsight_memory.models import Incident, MemoryEvidence
from innovation.anti_runbooks import build_anti_runbook_warnings


def evidence(item: Incident) -> MemoryEvidence:
    raw = incident_content(item)
    return MemoryEvidence(text=raw, raw_text=raw, incident_id=item.id)


def past_incident(incident_id: str, outcome: str, *, notes: str = "") -> Incident:
    return Incident(
        id=incident_id,
        service="payments-api",
        error="database pool exhaustion",
        category="Database",
        verified_cause=f"Cause recorded for {incident_id}",
        engineer_notes=notes or None,
        outcome=outcome,
        resolution_steps=["Increase the connection timeout"],
    )


def test_warning_reports_failure_count_context_and_incident_ids():
    recalled = [
        evidence(past_incident("resolved-1", "resolved")),
        evidence(past_incident("partial-2", "partial")),
        evidence(past_incident("failed-3", "failed", notes="Timeouts worsened after changing the limit")),
    ]
    warning, = build_anti_runbook_warnings(recalled)
    assert warning.failed_count == 1
    assert warning.attempted_count == 3
    assert warning.failed_incident_ids == ["failed-3"]
    assert "Tried before and failed in 1 of 3 recorded cases" in warning.message
    assert "Timeouts worsened" in warning.context[0]
    assert "Cause recorded for failed-3" in warning.context[0]


def test_warning_only_appears_when_a_failure_was_recorded():
    recalled = [evidence(past_incident("resolved-1", "resolved")), evidence(past_incident("partial-2", "partial"))]
    assert build_anti_runbook_warnings(recalled) == []


def test_duplicate_recall_units_for_one_incident_do_not_inflate_counts():
    failed = evidence(past_incident("failed-3", "failed"))
    warning, = build_anti_runbook_warnings([failed, failed])
    assert warning.failed_count == 1
    assert warning.attempted_count == 1


class FixedLLM:
    async def complete_json(self, *, model, messages):
        return json.dumps({
            "hypotheses": [],
            "recommended_steps": ["Inspect connection pool metrics"],
            "runbook_ref": "runbooks/database_failure.md",
        })


@pytest.mark.asyncio
async def test_anti_runbooks_are_opt_in_and_default_phase4_analysis_stays_unchanged():
    failed = past_incident("failed-3", "failed", notes="The timeout increase worsened latency")
    analyzer = RootCauseAnalyzer(FakeMemory([failed]), FixedLLM())
    incident = Incident(id="current", service="payments-api", error="database pool exhaustion", category="Database")
    default_result = await analyzer.analyze(incident)
    enabled_result = await analyzer.analyze(incident, innovation_enabled=True)
    assert default_result.anti_runbook_warnings == []
    assert len(default_result.warnings) == 1
    assert enabled_result.anti_runbook_warnings[0].failed_count == 1
    assert enabled_result.warnings[-1].startswith("Tried before and failed in 1 of 1")
    assert default_result.analysis == enabled_result.analysis
