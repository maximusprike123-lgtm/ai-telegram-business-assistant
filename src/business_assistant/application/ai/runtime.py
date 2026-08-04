"""Bounded provider-neutral AI execution with validation and deterministic degradation."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from uuid import uuid4

from .models import (
    AICompletionStatus,
    AIExecution,
    AIFailureCode,
    AIOperationRecord,
    AIRequest,
    ModelPolicy,
    ProviderRequest,
)
from .ports import (
    AIBusinessValidator,
    AIProviderError,
    AIProviderRegistryPort,
    AITelemetryPort,
    ModelPolicyPort,
    PromptCatalogPort,
    Sleep,
)
from .schemas import (
    AISchemaValidationError,
    confidence_of,
    fallback_result,
    json_schema_for,
    parse_result,
)


class AIRuntime:
    def __init__(
        self,
        *,
        enabled: bool,
        providers: AIProviderRegistryPort,
        prompts: PromptCatalogPort,
        policies: ModelPolicyPort,
        telemetry: AITelemetryPort,
        business_validator: AIBusinessValidator | None = None,
        sleep: Sleep = asyncio.sleep,
        timer: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._enabled = enabled
        self._providers = providers
        self._prompts = prompts
        self._policies = policies
        self._telemetry = telemetry
        self._business_validator = business_validator
        self._sleep = sleep
        self._timer = timer
        self._now = now

    async def execute(self, request: AIRequest) -> AIExecution:
        started = self._timer()
        if not self._enabled:
            execution = AIExecution(
                AICompletionStatus.DISABLED,
                fallback_result(request),
                AIFailureCode.DISABLED,
                0,
            )
            await self._record(request, None, execution, started, 0, 0)
            return execution

        policy = self._policies.for_task(request.task)
        if policy is None:
            return await self._fallback(
                request, None, AIFailureCode.POLICY_INVALID, 0, started, 0, 0
            )
        prompt = self._prompts.get(policy.prompt_id, policy.prompt_version)
        provider = self._providers.resolve(policy.provider)
        if (
            prompt is None
            or prompt.deprecated
            or prompt.task is not request.task
            or policy.schema_id not in prompt.compatible_schemas
            or provider is None
        ):
            return await self._fallback(
                request, policy, AIFailureCode.POLICY_INVALID, 0, started, 0, 0
            )
        try:
            rendered_prompt = prompt.render(request.prompt_variables)
        except ValueError:
            return await self._fallback(
                request, policy, AIFailureCode.POLICY_INVALID, 0, started, 0, 0
            )

        provider_request = ProviderRequest(
            request.task,
            policy.model,
            rendered_prompt,
            request.input_text,
            policy.schema_id,
            json_schema_for(request),
            policy.temperature,
            policy.max_output_tokens,
        )
        attempts = 0
        input_tokens = output_tokens = 0
        while attempts <= policy.max_retries:
            attempts += 1
            try:
                async with asyncio.timeout(policy.timeout_seconds):
                    response = await provider.execute(provider_request)
                input_tokens, output_tokens = response.input_tokens, response.output_tokens
                if response.provider != policy.provider or response.model != policy.model:
                    raise AIProviderError("provider_identity_mismatch", retryable=False)
                result = parse_result(request, response.output)
                if self._business_validator is not None:
                    self._business_validator.validate(request, result)
                if confidence_of(result) < policy.confidence_threshold:
                    return await self._fallback(
                        request,
                        policy,
                        AIFailureCode.LOW_CONFIDENCE,
                        attempts,
                        started,
                        input_tokens,
                        output_tokens,
                    )
                execution = AIExecution(AICompletionStatus.SUCCESS, result, None, attempts)
                await self._record(request, policy, execution, started, input_tokens, output_tokens)
                return execution
            except asyncio.CancelledError:
                execution = AIExecution(
                    AICompletionStatus.CANCELLED,
                    fallback_result(request),
                    AIFailureCode.CANCELLED,
                    attempts,
                )
                await self._record(request, policy, execution, started, input_tokens, output_tokens)
                raise
            except TimeoutError:
                failure = AIFailureCode.TIMEOUT
                retryable = True
            except AISchemaValidationError:
                failure = AIFailureCode.INVALID_OUTPUT
                retryable = False
            except AIProviderError as exc:
                failure = _provider_failure(exc.code)
                retryable = exc.retryable
            except ValueError:
                failure = AIFailureCode.INVALID_OUTPUT
                retryable = False
            except Exception:
                failure = AIFailureCode.PROVIDER_UNAVAILABLE
                retryable = False
            if not retryable or attempts > policy.max_retries:
                return await self._fallback(
                    request,
                    policy,
                    failure,
                    attempts,
                    started,
                    input_tokens,
                    output_tokens,
                )
            await self._sleep(min(2 ** (attempts - 1) * 0.1, 2.0))
        raise AssertionError("AI retry loop must return")

    async def _fallback(
        self,
        request: AIRequest,
        policy: ModelPolicy | None,
        failure: AIFailureCode,
        attempts: int,
        started: float,
        input_tokens: int,
        output_tokens: int,
    ) -> AIExecution:
        execution = AIExecution(
            AICompletionStatus.FALLBACK, fallback_result(request), failure, attempts
        )
        await self._record(request, policy, execution, started, input_tokens, output_tokens)
        return execution

    async def _record(
        self,
        request: AIRequest,
        policy: ModelPolicy | None,
        execution: AIExecution,
        started: float,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        provider = policy.provider if policy is not None else "none"
        model = policy.model if policy is not None else "none"
        prompt_id = policy.prompt_id if policy is not None else "none"
        prompt_version = policy.prompt_version if policy is not None else 0
        schema_id = policy.schema_id if policy is not None else "none"
        cost = _cost(policy, input_tokens, output_tokens)
        record = AIOperationRecord(
            uuid4(),
            request.tenant_id,
            request.conversation_id,
            request.correlation_id,
            request.task,
            provider,
            model,
            prompt_id,
            prompt_version,
            schema_id,
            execution.status,
            execution.attempts,
            max(0, round((self._timer() - started) * 1000)),
            input_tokens,
            output_tokens,
            cost,
            execution.failure_code,
            self._now(),
        )
        try:
            await self._telemetry.record(record)
        except Exception:
            # Telemetry cannot turn a safe fallback or validated result into a workflow failure.
            return


def _provider_failure(code: str) -> AIFailureCode:
    if code == "rate_limited":
        return AIFailureCode.RATE_LIMITED
    if code == "timeout":
        return AIFailureCode.TIMEOUT
    if code == "refused":
        return AIFailureCode.REFUSED
    if code in {"invalid_response", "incomplete"}:
        return AIFailureCode.INVALID_OUTPUT
    return AIFailureCode.PROVIDER_UNAVAILABLE


def _cost(policy: ModelPolicy | None, input_tokens: int, output_tokens: int) -> Decimal:
    if policy is None:
        return Decimal(0)
    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * policy.input_cost_per_million
        + Decimal(output_tokens) * policy.output_cost_per_million
    ) / million
