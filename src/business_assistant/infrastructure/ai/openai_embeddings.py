"""OpenAI embeddings adapter behind the application embedding port."""

import math
from collections.abc import Mapping, Sequence

import httpx

from business_assistant.application.ai import AIProviderError


class OpenAIEmbeddingsAdapter:
    provider_name = "openai"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        self._client = client
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/embeddings"

    async def embed(
        self, texts: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        if not texts or len(texts) > 100 or any(not text.strip() for text in texts):
            raise ValueError("Embedding input batch is invalid")
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": model,
                    "input": list(texts),
                    "encoding_format": "float",
                    "dimensions": dimensions,
                },
            )
        except httpx.TimeoutException as exc:
            raise AIProviderError("timeout", retryable=True) from exc
        except httpx.RequestError as exc:
            raise AIProviderError("unavailable", retryable=True) from exc
        if response.status_code == 429:
            raise AIProviderError("rate_limited", retryable=True)
        if response.status_code in {408, 409} or response.status_code >= 500:
            raise AIProviderError("unavailable", retryable=True)
        if response.status_code >= 400:
            raise AIProviderError("request_rejected", retryable=False)
        try:
            body = response.json()
            if not isinstance(body, Mapping) or body.get("model") != model:
                raise ValueError("Embedding response identity is invalid")
            data = body.get("data")
            if isinstance(data, (str, bytes)) or not isinstance(data, Sequence):
                raise ValueError("Embedding response data is missing")
            indexed: dict[int, tuple[float, ...]] = {}
            for raw in data:
                if not isinstance(raw, Mapping) or raw.get("object") != "embedding":
                    raise ValueError("Embedding response item is invalid")
                index, vector = raw.get("index"), raw.get("embedding")
                if isinstance(index, bool) or not isinstance(index, int):
                    raise ValueError("Embedding response index is invalid")
                if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence):
                    raise ValueError("Embedding response vector is invalid")
                values = tuple(float(value) for value in vector)
                if len(values) != dimensions or any(not math.isfinite(value) for value in values):
                    raise ValueError("Embedding response dimensions are invalid")
                indexed[index] = values
            if set(indexed) != set(range(len(texts))):
                raise ValueError("Embedding response batch is incomplete")
            return tuple(indexed[index] for index in range(len(texts)))
        except (TypeError, ValueError) as exc:
            raise AIProviderError("invalid_response", retryable=False) from exc
