from types import SimpleNamespace

import pytest

from agent.llm_client import GroqChatModel


class FakeCompletions:
    def __init__(self, failures=0, *, content="{}", tool_calls=None):
        self.failures = failures
        self.content = content
        self.tool_calls = tool_calls
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise TimeoutError("simulated request timeout")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content, tool_calls=self.tool_calls))])


class FakeGroqClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


@pytest.mark.asyncio
async def test_groq_timeout_retries_and_uses_supported_json_object_mode(monkeypatch):
    completions = FakeCompletions(failures=1, content='{"ok":true}')
    model = GroqChatModel("test-key", client=FakeGroqClient(completions), retries=1)

    async def no_wait(_):
        return None

    monkeypatch.setattr("agent.llm_client.asyncio.sleep", no_wait)
    result = await model.complete_json(model="qwen/qwen3-32b", messages=[{"role": "user", "content": "Return JSON"}])
    assert result == '{"ok":true}'
    assert len(completions.calls) == 2
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_groq_tool_call_response_is_reported_for_pydantic_repair():
    completions = FakeCompletions(content=None, tool_calls=[{"id": "call-1"}])
    model = GroqChatModel("test-key", client=FakeGroqClient(completions), retries=0)
    with pytest.raises(ValueError, match="tool calls"):
        await model.complete_json(model="qwen/qwen3-32b", messages=[])
