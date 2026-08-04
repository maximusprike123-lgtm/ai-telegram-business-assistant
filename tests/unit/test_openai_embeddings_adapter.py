import json

import httpx
import pytest

from business_assistant.application.ai import AIProviderError
from business_assistant.infrastructure.ai import OpenAIEmbeddingsAdapter


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_openai_embeddings_contract_preserves_batch_order_and_dimensions() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer local-fixture-key"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "embedding-fixture",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    async with client(handler) as http:
        result = await OpenAIEmbeddingsAdapter(http, "local-fixture-key").embed(
            ("first", "second"), model="embedding-fixture", dimensions=3
        )
    assert result == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert captured == {
        "model": "embedding-fixture",
        "input": ["first", "second"],
        "encoding_format": "float",
        "dimensions": 3,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [(429, "rate_limited", True), (503, "unavailable", True), (400, "request_rejected", False)],
)
async def test_openai_embeddings_errors_are_safe(status: int, code: str, retryable: bool) -> None:
    async with client(
        lambda _: httpx.Response(status, json={"error": "provider-secret-must-not-leak"})
    ) as http:
        with pytest.raises(AIProviderError) as captured:
            await OpenAIEmbeddingsAdapter(http, "local-fixture-key").embed(
                ("query",), model="embedding-fixture", dimensions=3
            )
    assert captured.value.code == code
    assert captured.value.retryable is retryable
    assert "provider-secret" not in str(captured.value)


@pytest.mark.asyncio
async def test_openai_embeddings_rejects_malformed_or_incomplete_vectors() -> None:
    async with client(
        lambda _: httpx.Response(
            200,
            json={
                "model": "embedding-fixture",
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0]}],
            },
        )
    ) as http:
        with pytest.raises(AIProviderError) as captured:
            await OpenAIEmbeddingsAdapter(http, "local-fixture-key").embed(
                ("query",), model="embedding-fixture", dimensions=3
            )
    assert captured.value.code == "invalid_response"
