"""OpenAI Responses API adapter isolated behind the provider-neutral model port."""

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

import httpx

from business_assistant.application.ai import (
    AIProviderError,
    ProviderRequest,
    ProviderResponse,
)


class OpenAIResponsesAdapter:
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
        self._url = f"{base_url.rstrip('/')}/responses"

    async def execute(self, request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_input},
            ],
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "strict": True,
                    "schema": dict(request.json_schema),
                }
            },
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
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
            decoded = response.json()
            if not isinstance(decoded, Mapping):
                raise ValueError("Provider response must be an object")
            body = cast(Mapping[str, object], decoded)
            if body.get("status") != "completed":
                raise AIProviderError("incomplete", retryable=False)
            output = _structured_output(body.get("output"))
            usage = _usage(body.get("usage"))
            model = body.get("model")
            if not isinstance(model, str) or model != request.model:
                raise AIProviderError("provider_identity_mismatch", retryable=False)
            return ProviderResponse(
                self.provider_name,
                model,
                output,
                usage[0],
                usage[1],
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError("invalid_response", retryable=False) from exc


def _structured_output(value: object) -> Mapping[str, Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("Provider output is missing")
    for output in value:
        if not isinstance(output, Mapping) or output.get("type") != "message":
            continue
        content = output.get("content")
        if isinstance(content, (str, bytes)) or not isinstance(content, Sequence):
            continue
        for item in content:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == "refusal":
                raise AIProviderError("refused", retryable=False)
            if item.get("type") != "output_text" or not isinstance(item.get("text"), str):
                continue
            parsed = json.loads(cast(str, item["text"]))
            if not isinstance(parsed, Mapping):
                raise ValueError("Structured output must be an object")
            return cast(Mapping[str, Any], parsed)
    raise ValueError("Provider output text is missing")


def _usage(value: object) -> tuple[int, int]:
    if not isinstance(value, Mapping):
        raise ValueError("Provider usage is missing")
    input_tokens, output_tokens = value.get("input_tokens"), value.get("output_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or input_tokens < 0
        or output_tokens < 0
    ):
        raise ValueError("Provider usage is invalid")
    return input_tokens, output_tokens
