import pytest

from agent.root_cause_analyzer import RootCauseAnalyzer
from agent.runbook_recommender import RUNBOOKS, runbook_steps
from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident


def current_incident():
    return Incident(
        id="current-1",
        service="payments-api",
        error="database connection pool exhausted",
        severity="high",
        category="Database",
        symptoms=["request timeouts"],
    )


def history_incident():
    return Incident(
        id="history-1",
        service="payments-api",
        error="database connection pool exhausted",
        severity="high",
        category="Database",
        outcome="resolved",
        verified_cause="unclosed database sessions exhausted the pool",
        resolution_steps=["Fixed session cleanup"],
    )


def response_json(ids=None):
    return {
        "hypotheses": [{
            "cause": "Database sessions may not be closed reliably",
            "evidence_incident_ids": ids or ["history-1"],
            "reasoning": "A recalled incident for the same service recorded pool exhaustion after leaked sessions.",
            "status": "suspected",
        }],
        "recommended_steps": ["Review session cleanup in affected workers"],
        "runbook_ref": "invented.md",
    }


class QueueLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, *, model, messages):
        self.calls.append({"model": model, "messages": messages})
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def json_response(value):
    import json

    return json.dumps(value)


@pytest.mark.parametrize("category", ["Database", "API", "Overload", "Network", "Deployment", "Performance"])
def test_each_supported_category_has_a_markdown_runbook(category):
    reference, steps = runbook_steps(category)
    assert reference == RUNBOOKS[category]
    assert reference.endswith(".md")
    assert steps


@pytest.mark.asyncio
async def test_valid_analysis_uses_recalled_ids_and_merges_verified_fix_steps():
    llm = QueueLLM(json_response(response_json()))
    analyzer = RootCauseAnalyzer(FakeMemory([history_incident()]), llm)
    result = await analyzer.analyze(current_incident())
    assert result.analysis.hypotheses[0].evidence_incident_ids == ["history-1"]
    assert result.analysis.hypotheses[0].status == "suspected"
    assert "Previously successful in incident history-1: Fixed session cleanup" in result.analysis.recommended_steps
    assert result.analysis.runbook_ref == "runbooks/database_failure.md"
    assert result.memory_available
    assert not result.used_fallback


@pytest.mark.asyncio
async def test_hallucinated_incident_ids_are_removed_and_flagged():
    llm = QueueLLM(json_response(response_json(["history-1", "not-recalled"])))
    analyzer = RootCauseAnalyzer(FakeMemory([history_incident()]), llm)
    result = await analyzer.analyze(current_incident())
    assert result.analysis.hypotheses[0].evidence_incident_ids == ["history-1"]
    assert result.warnings == ["Unrecalled incident IDs were removed from the analysis."]


@pytest.mark.asyncio
async def test_cold_start_says_no_relevant_experience_and_skips_llm():
    llm = QueueLLM(json_response(response_json()))
    analyzer = RootCauseAnalyzer(FakeMemory(), llm)
    result = await analyzer.analyze(current_incident())
    assert result.cold_start
    assert result.memory_available
    assert "No relevant experience" in result.message
    assert result.analysis.hypotheses == []
    assert result.analysis.recommended_steps
    assert not llm.calls


@pytest.mark.asyncio
async def test_malformed_json_is_repaired_once_with_repair_prompt():
    llm = QueueLLM("not json", json_response(response_json()))
    analyzer = RootCauseAnalyzer(FakeMemory([history_incident()]), llm)
    result = await analyzer.analyze(current_incident())
    assert not result.used_fallback
    assert len(llm.calls) == 2
    assert "Repair your previous response" in llm.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_tool_call_shaped_response_is_validated_then_repaired():
    llm = QueueLLM(json_response({"tool_calls": [{"name": "execute_fix"}]}), json_response(response_json()))
    analyzer = RootCauseAnalyzer(FakeMemory([history_incident()]), llm)
    result = await analyzer.analyze(current_incident())
    assert not result.used_fallback
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_runbook_only():
    llm = QueueLLM(RuntimeError("simulated Groq tool-call failure"))
    analyzer = RootCauseAnalyzer(FakeMemory([history_incident()]), llm)
    result = await analyzer.analyze(current_incident())
    assert result.used_fallback
    assert result.analysis.hypotheses == []
    assert result.analysis.runbook_ref == "runbooks/database_failure.md"
    assert result.analysis.recommended_steps


@pytest.mark.asyncio
async def test_memory_unavailable_is_not_misreported_as_empty_memory():
    memory = FakeMemory()
    memory.last_error = "hindsight_unavailable"
    analyzer = RootCauseAnalyzer(memory, QueueLLM())
    result = await analyzer.analyze(current_incident())
    assert not result.memory_available
    assert "memory is unavailable" in result.message.lower()
    assert "No relevant experience" not in result.message


@pytest.mark.asyncio
async def test_missing_integrations_keep_analysis_on_deterministic_runbook_path():
    result = await RootCauseAnalyzer(memory=None, llm=None).analyze(current_incident())
    assert not result.memory_available
    assert result.used_fallback
    assert result.analysis.runbook_ref == "runbooks/database_failure.md"
    assert result.analysis.recommended_steps
    assert "no historical evidence" in result.message.lower()
