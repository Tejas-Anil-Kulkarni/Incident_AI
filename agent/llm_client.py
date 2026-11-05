"""Resilient Groq Chat Completions adapter."""

import asyncio
import logging
import random
from typing import Any

from groq import Groq

logger = logging.getLogger(__name__)


class GroqChatModel:
    """Calls Groq's official Python SDK using valid-JSON response mode."""

    def __init__(self, api_key: str, *, timeout: float = 20.0, retries: int = 2, client: Any = None) -> None:
        self._client = client or Groq(api_key=api_key, timeout=timeout, max_retries=0)
        self._timeout = timeout
        self._retries = max(0, retries)

    async def complete_json(self, *, model: str, messages: list[dict[str, str]]) -> str:
        for attempt in range(self._retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._client.chat.completions.create,
                        model=model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0,
                    ),
                    timeout=self._timeout + 1.0,
                )
                message = response.choices[0].message
                content = message.content
                if content:
                    return content
                if getattr(message, "tool_calls", None):
                    raise ValueError("Groq returned tool calls instead of the requested JSON object")
                raise ValueError("Groq returned an empty response")
            except ValueError:
                raise
            except Exception as exc:
                if attempt >= self._retries or not _is_transient(exc):
                    logger.warning("Groq request failed: %s", type(exc).__name__)
                    raise
                delay = 0.4 * (2**attempt) * random.uniform(0.8, 1.2)
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable retry state")

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


def _is_transient(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    return (
        isinstance(error, (TimeoutError, asyncio.TimeoutError, ConnectionError))
        or error.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}
        or status_code in {408, 409, 429}
        or isinstance(status_code, int) and status_code >= 500
    )
