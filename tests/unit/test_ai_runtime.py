import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from business_assistant.application.ai import (
    AdvisoryRoutingValidator,
    AICompletionStatus,
    AIFailureCode,
    AIProviderError,
    AIRequest,
    AIRuntime,
    AISchemaValidationError,
    AITask,
    Intent,
    IntentResult,
    ModelPolicy,
    PromptTemplate,
    ProviderRequest,
    ProviderResponse,
    SuggestedAction,
    parse_result,
)
from business_assistant.domain.shared import ConversationId, TenantId


def request(task: AITask = AITask.INTENT) -> AIRequest:
    return AIRequest(
        TenantId.new(),
        ConversationId.new(),
        uuid4(),
        task,
        "When are you open?",
        allowed_extraction_fields=frozenset({"service"})
        if task is AITask.EXTRACTION
        else frozenset(),
        allowed_classification_labels=frozenset({"safe"})
        if task is AITask.CLASSIFICATION
        else frozenset(),
    )


def intent_output(*, confidence: float = 0.95, action: str = "show_hours") -> dict[str, Any]:
    return {
        "intent": "business_hours",
        "confidence": confidence,
        "entities": [],
        "missing_information": [],
        "risk_flags": [],
        "suggested_action": action,
        "rationale_category": "hours_request",
    }


class Provider:
    provider_name = "fixture"

    def __init__(self, responses: list[ProviderResponse | Exception]) -> None:
        self.responses = responses
        self.requests: list[ProviderRequest] = []

    async def execute(self, provider_request: ProviderRequest) -> ProviderResponse:
        self.requests.append(provider_request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class Registry:
    def __init__(self, provider: Provider | None) -> None:
        self.provider = provider

    def resolve(self, provider: str) -> Provider | None:
        return self.provider if provider == "fixture" else None


class Catalog:
    prompt = PromptTemplate(
        "router",
        1,
        AITask.INTENT,
        "Classify the request safely.",
        frozenset(),
        frozenset({"intent-v1"}),
    )

    def get(self, identifier: str, version: int) -> PromptTemplate | None:
        return self.prompt if (identifier, version) == ("router", 1) else None


class Policies:
    policy = ModelPolicy(
        AITask.INTENT,
        "fixture",
        "fixture-model",
        "router",
        1,
        "intent-v1",
        0,
        200,
        0.05,
        1,
        0.8,
        "strict_json_schema",
        Decimal("1.5"),
        Decimal("3"),
    )

    def for_task(self, task: AITask) -> ModelPolicy | None:
        return self.policy if task is AITask.INTENT else None


class Telemetry:
    def __init__(self) -> None:
        self.records = []

    async def record(self, operation) -> None:
        self.records.append(operation)


def response(output: dict[str, Any]) -> ProviderResponse:
    return ProviderResponse("fixture", "fixture-model", output, 100, 20)


def runtime(provider: Provider | None, telemetry: Telemetry, *, enabled: bool = True) -> AIRuntime:
    return AIRuntime(
        enabled=enabled,
        providers=Registry(provider),
        prompts=Catalog(),
        policies=Policies(),
        telemetry=telemetry,
        business_validator=AdvisoryRoutingValidator(),
        sleep=lambda _: asyncio.sleep(0),
        now=lambda: datetime(2026, 8, 4, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_valid_output_passes_schema_application_confidence_and_telemetry() -> None:
    provider = Provider([response(intent_output())])
    telemetry = Telemetry()
    result = await runtime(provider, telemetry).execute(request())
    assert result.status is AICompletionStatus.SUCCESS
    assert isinstance(result.result, IntentResult)
    assert result.result.intent is Intent.BUSINESS_HOURS
    assert provider.requests[0].json_schema["additionalProperties"] is False
    assert telemetry.records[0].input_tokens == 100
    assert telemetry.records[0].estimated_cost == Decimal("0.00021")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "failure"),
    [
        ({"intent": "business_hours"}, AIFailureCode.INVALID_OUTPUT),
        (intent_output(confidence=0.2), AIFailureCode.LOW_CONFIDENCE),
        (intent_output(action="none") | {"intent": "high_risk"}, AIFailureCode.INVALID_OUTPUT),
        (intent_output(action="show_catalog"), AIFailureCode.INVALID_OUTPUT),
    ],
)
async def test_invalid_low_confidence_and_unsafe_outputs_degrade(
    output: dict[str, Any], failure: AIFailureCode
) -> None:
    result = await runtime(Provider([response(output)]), Telemetry()).execute(request())
    assert result.status is AICompletionStatus.FALLBACK
    assert result.failure_code is failure
    assert isinstance(result.result, IntentResult)
    assert result.result.suggested_action is SuggestedAction.OFFER_HUMAN


@pytest.mark.asyncio
async def test_transient_failure_retries_then_succeeds_and_permanent_failure_does_not() -> None:
    transient = Provider(
        [AIProviderError("unavailable", retryable=True), response(intent_output())]
    )
    succeeded = await runtime(transient, Telemetry()).execute(request())
    assert succeeded.status is AICompletionStatus.SUCCESS and succeeded.attempts == 2

    permanent = Provider([AIProviderError("refused", retryable=False)])
    failed = await runtime(permanent, Telemetry()).execute(request())
    assert failed.failure_code is AIFailureCode.REFUSED and failed.attempts == 1


@pytest.mark.asyncio
async def test_timeout_missing_policy_and_disabled_runtime_use_deterministic_fallback() -> None:
    class SlowProvider(Provider):
        async def execute(self, provider_request: ProviderRequest) -> ProviderResponse:
            await asyncio.sleep(0.2)
            return response(intent_output())

    timed_out = await runtime(SlowProvider([]), Telemetry()).execute(request())
    assert timed_out.failure_code is AIFailureCode.TIMEOUT and timed_out.attempts == 2

    disabled_telemetry = Telemetry()
    disabled = await runtime(None, disabled_telemetry, enabled=False).execute(request())
    assert disabled.status is AICompletionStatus.DISABLED and disabled.attempts == 0
    assert disabled_telemetry.records[0].provider == "none"


@pytest.mark.asyncio
async def test_cancellation_is_recorded_and_propagated() -> None:
    class CancelProvider(Provider):
        async def execute(self, provider_request: ProviderRequest) -> ProviderResponse:
            raise asyncio.CancelledError

    telemetry = Telemetry()
    with pytest.raises(asyncio.CancelledError):
        await runtime(CancelProvider([]), telemetry).execute(request())
    assert telemetry.records[0].status is AICompletionStatus.CANCELLED


def test_all_structured_results_are_strict_and_prompt_versions_validate() -> None:
    with pytest.raises(AISchemaValidationError):
        parse_result(request(), intent_output() | {"unexpected": True})
    with pytest.raises(AISchemaValidationError):
        parse_result(
            request(AITask.EXTRACTION),
            {
                "fields": [{"key": "forbidden", "value": "x", "confidence": 1}],
                "confidence": 1,
            },
        )
    prompt = PromptTemplate(
        "extract",
        2,
        AITask.EXTRACTION,
        "Allowed scope: {scope}",
        frozenset({"scope"}),
        frozenset({"extraction-v1"}),
        {"owner": "platform"},
    )
    assert prompt.render({"scope": "service request"}).endswith("service request")
    with pytest.raises(ValueError, match="variables"):
        prompt.render({})
    with pytest.raises(ValueError, match="variables"):
        replace(prompt, variables=frozenset())


@pytest.mark.parametrize(
    ("task", "output"),
    [
        (
            AITask.EXTRACTION,
            {
                "fields": [{"key": "service", "value": "inspection", "confidence": 0.9}],
                "confidence": 0.9,
            },
        ),
        (
            AITask.CLASSIFICATION,
            {"label": "safe", "confidence": 0.9, "rationale_category": "safe_request"},
        ),
        (AITask.REWRITE, {"text": "Rewritten text", "confidence": 0.9}),
        (
            AITask.SUMMARY,
            {"summary": "Short summary", "key_points": ["One fact"], "confidence": 0.9},
        ),
    ],
)
def test_each_structured_task_schema_parses_valid_output(
    task: AITask, output: dict[str, Any]
) -> None:
    assert parse_result(request(task), output).confidence == 0.9


def test_intent_schema_exposes_no_consequential_actions() -> None:
    from business_assistant.application.ai import json_schema_for

    actions = json_schema_for(request())["properties"]["suggested_action"]["enum"]
    assert not set(actions) & {
        "create_booking",
        "confirm_booking",
        "cancel_booking",
        "update_lead",
        "delete_information",
    }
