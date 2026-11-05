import os

import pytest

from agent.llm_client import GroqChatModel
from agent.root_cause_analyzer import RootCauseAnalyzer
from hindsight_memory.fake_memory import FakeMemory
from hindsight_memory.models import Incident

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_groq_can_return_a_valid_analysis_draft():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        pytest.skip("Groq integration credentials are not configured")
    memory = FakeMemory([Incident(
        id="groq-smoke-history",
        service="payments-api",
        error="database connection pool timeout",
        severity="high",
        category="Database",
        outcome="resolved",
        verified_cause="sessions leaked",
        resolution_steps=["Fixed session cleanup"],
    )])
    model = GroqChatModel(api_key)
    try:
        result = await RootCauseAnalyzer(memory, model).analyze(Incident(
            id="groq-smoke-current",
            service="payments-api",
            error="database connection pool timeout",
            severity="high",
            category="Database",
        ))
        assert not result.used_fallback
    finally:
        await model.close()
