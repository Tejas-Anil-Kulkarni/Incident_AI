"""Guard the adapter against drift from the installed official SDK surface."""

import inspect

from hindsight_client import Hindsight


def test_official_sdk_exposes_methods_and_parameters_used_by_adapter() -> None:
    assert {"base_url", "api_key", "timeout"} <= set(inspect.signature(Hindsight).parameters)
    assert {"bank_id", "reflect_mission"} <= set(inspect.signature(Hindsight.create_bank).parameters)
    assert {
        "bank_id", "content", "context", "document_id", "metadata", "tags",
        "retain_async", "operation_id",
    } <= set(inspect.signature(Hindsight.retain).parameters)
    assert {"bank_id", "query", "max_tokens", "include_chunks", "max_chunk_tokens"} <= set(inspect.signature(Hindsight.recall).parameters)
    assert {"bank_id", "query"} <= set(inspect.signature(Hindsight.reflect).parameters)
