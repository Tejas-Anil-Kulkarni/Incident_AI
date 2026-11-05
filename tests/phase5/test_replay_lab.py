import json

import pytest

from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident
from innovation.replay_lab import ReplayLab


class ReplayLLM:
    def __init__(self):
        self.current_payloads = []

    async def complete_json(self, *, model, messages):
        payload = json.loads(messages[1]["content"])
        current = payload["current_incident"]
        self.current_payloads.append(current)
        evidence = payload["recalled_evidence"]
        if evidence:
            cited_id = evidence[0]["incident_id"]
            steps = ["Close unclosed database sessions before returning the connection"]
            hypotheses = [{
                "cause": "Database sessions may be leaked",
                "evidence_incident_ids": [cited_id],
                "reasoning": "A recalled connection-pool incident records session leaks.",
                "status": "suspected",
            }]
        else:
            steps = ["Inspect current database connection metrics"]
            hypotheses = []
        return json.dumps({
            "hypotheses": hypotheses,
            "recommended_steps": steps,
            "runbook_ref": "runbooks/database_failure.md",
        })


def sequence():
    return [
        Incident(
            id="pool-history-1",
            service="payments-api",
            error="database connection pool exhausted",
            category="Database",
            severity="high",
            symptoms=["request timeouts"],
            verified_cause="Unclosed database sessions exhausted the pool",
            resolution_steps=["Close unclosed database sessions before returning the connection"],
            outcome="resolved",
        ),
        Incident(
            id="pool-current-2",
            service="payments-api",
            error="database connection pool exhausted",
            category="Database",
            severity="high",
            symptoms=["request timeouts"],
            suspected_cause="Possible connection leak",
            verified_cause="Unclosed database sessions exhausted the pool",
            resolution_steps=["Close unclosed database sessions before returning the connection"],
            outcome="resolved",
        ),
    ]


@pytest.mark.asyncio
async def test_replay_emits_chart_ready_metrics_for_both_memory_modes():
    llm = ReplayLLM()
    result = await ReplayLab(llm, model_name="test-model").run(sequence(), FakeMemory(), run_id="fixed-run")

    assert result.run_id == "fixed-run"
    assert result.incidents_replayed == 2
    assert [step.step for step in result.memory_disabled.steps] == [1, 2]
    assert [step.step for step in result.memory_enabled.steps] == [1, 2]
    assert result.memory_disabled.steps[1].correct_prior_cause_cited is False
    assert result.memory_disabled.steps[1].steps_to_verified_fix is None
    assert result.memory_enabled.steps[1].correct_prior_cause_cited is True
    assert result.memory_enabled.steps[1].matched_verified_cause == sequence()[0].verified_cause
    assert result.memory_enabled.steps[1].steps_to_verified_fix == 1
    assert result.memory_enabled.steps[1].memory_write_success is True
    assert "No aggregate success rate" in result.notes[-1]


@pytest.mark.asyncio
async def test_replay_hides_answer_labels_from_the_current_incident_prompt():
    llm = ReplayLLM()
    await ReplayLab(llm, model_name="test-model").run(sequence(), FakeMemory(), run_id="fixed-run")
    for payload in llm.current_payloads:
        assert payload["verified_cause"] is None
        assert payload["resolution_steps"] == []
        assert payload["outcome"] == "unknown"
        assert payload["suspected_cause"] is None


@pytest.mark.asyncio
async def test_fixed_sequence_and_mocked_llm_produce_identical_learning_curve():
    lab = ReplayLab(ReplayLLM(), model_name="test-model")
    first = await lab.run(sequence(), FakeMemory(), run_id="fixed-run")
    second = await lab.run(sequence(), FakeMemory(), run_id="fixed-run")
    assert first.model_dump() == second.model_dump()


def test_replay_request_rejects_duplicate_or_empty_sequences():
    from pydantic import ValidationError

    from innovation.replay_lab import ReplayRequest

    with pytest.raises(ValidationError):
        ReplayRequest(incident_ids=[])
    with pytest.raises(ValidationError):
        ReplayRequest(incident_ids=["same", "same"])
