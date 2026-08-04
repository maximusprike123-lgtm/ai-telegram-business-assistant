import json
from typing import Any

import httpx
import pytest

from business_assistant.application.ai import AIProviderError, AITask, ProviderRequest
from business_assistant.infrastructure.ai import OpenAIResponsesAdapter


def provider_request() -> ProviderRequest:
    return ProviderRequest(
        AITask.INTENT,
        "configured-model",
        "System policy",
        "Customer input",
        "intent-v1",
        {
            "type": "object",
            "properties": {"intent": {"type": "string"}},
            "required": ["intent"],
            "additionalProperties": False,
        },
        0,
        200,
    )


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_openai_responses_adapter_sends_strict_schema_and_maps_safe_result() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer local-fixture-key"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"intent": "help"})}
                        ],
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
            },
        )

    async with client(handler) as http:
        result = await OpenAIResponsesAdapter(http, "local-fixture-key").execute(provider_request())
    assert result.output == {"intent": "help"}
    assert (result.input_tokens, result.output_tokens) == (12, 4)
    assert captured["store"] is False
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["input"][1] == {"role": "user", "content": "Customer input"}
    assert "tools" not in captured


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_code", "retryable"),
    [(429, "rate_limited", True), (503, "unavailable", True), (400, "request_rejected", False)],
)
async def test_openai_responses_adapter_classifies_http_failures_without_body_leakage(
    status: int, expected_code: str, retryable: bool
) -> None:
    async with client(
        lambda _: httpx.Response(status, json={"error": {"message": "sensitive provider body"}})
    ) as http:
        with pytest.raises(AIProviderError) as captured:
            await OpenAIResponsesAdapter(http, "local-fixture-key").execute(provider_request())
    assert captured.value.code == expected_code
    assert captured.value.retryable is retryable
    assert "sensitive provider body" not in str(captured.value)


@pytest.mark.asyncio
async def test_openai_responses_adapter_rejects_refusal_and_malformed_output() -> None:
    responses = iter(
        [
            {
                "status": "completed",
                "model": "configured-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "provider refusal text"}],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            {
                "status": "completed",
                "model": "configured-model",
                "output": [{"type": "message", "content": []}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    async with client(handler) as http:
        adapter = OpenAIResponsesAdapter(http, "local-fixture-key")
        with pytest.raises(AIProviderError) as refusal:
            await adapter.execute(provider_request())
        with pytest.raises(AIProviderError) as malformed:
            await adapter.execute(provider_request())
    assert refusal.value.code == "refused"
    assert malformed.value.code == "invalid_response"
