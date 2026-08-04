"""Inward-facing provider, policy, prompt, validation, and telemetry ports."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from .models import (
    AIOperationRecord,
    AIRequest,
    AIResult,
    AITask,
    ModelPolicy,
    PromptTemplate,
    ProviderRequest,
    ProviderResponse,
)


class AIProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__("AI provider request failed")


class AIModelPort(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def execute(self, request: ProviderRequest) -> ProviderResponse: ...


class AIProviderRegistryPort(Protocol):
    def resolve(self, provider: str) -> AIModelPort | None: ...


class PromptCatalogPort(Protocol):
    def get(self, identifier: str, version: int) -> PromptTemplate | None: ...


class ModelPolicyPort(Protocol):
    def for_task(self, task: AITask) -> ModelPolicy | None: ...


class AITelemetryPort(Protocol):
    async def record(self, operation: AIOperationRecord) -> None: ...


class AIBusinessValidator(Protocol):
    def validate(self, request: AIRequest, result: AIResult) -> None: ...


Sleep = Callable[[float], Awaitable[None]]
