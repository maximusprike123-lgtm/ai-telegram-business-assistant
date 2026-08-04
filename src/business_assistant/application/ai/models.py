"""Provider-neutral contracts for bounded AI tasks and safe runtime outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from string import Formatter
from types import MappingProxyType
from typing import Any
from uuid import UUID

from business_assistant.domain.shared import ConversationId, TenantId


class AITask(StrEnum):
    INTENT = "intent"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    REWRITE = "rewrite"
    SUMMARY = "summary"


class AICompletionStatus(StrEnum):
    SUCCESS = "success"
    FALLBACK = "fallback"
    DISABLED = "disabled"
    CANCELLED = "cancelled"


class AIFailureCode(StrEnum):
    DISABLED = "disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    LOW_CONFIDENCE = "low_confidence"
    REFUSED = "refused"
    CANCELLED = "cancelled"
    POLICY_INVALID = "policy_invalid"


class Intent(StrEnum):
    GREETING = "greeting"
    HELP = "help"
    BUSINESS_HOURS = "business_hours"
    LOCATION_CONTACT = "location_contact"
    SERVICE_DISCOVERY = "service_discovery"
    SERVICE_DETAIL = "service_detail"
    FAQ_KNOWLEDGE = "faq_knowledge"
    BOOK = "book"
    RESCHEDULE = "reschedule"
    CANCEL_BOOKING = "cancel_booking"
    BOOKING_STATUS = "booking_status"
    QUALIFY_LEAD = "qualify_lead"
    HUMAN_REQUEST = "human_request"
    COMPLAINT = "complaint"
    HIGH_RISK = "high_risk"
    UNSUPPORTED = "unsupported"
    SMALL_TALK = "small_talk"
    UNKNOWN = "unknown"


class SuggestedAction(StrEnum):
    SHOW_HOME = "show_home"
    SHOW_CATALOG = "show_catalog"
    SHOW_HOURS = "show_hours"
    ASK_CLARIFICATION = "ask_clarification"
    OFFER_HUMAN = "offer_human"
    NONE = "none"


class RiskFlag(StrEnum):
    COMPLAINT = "complaint"
    HIGH_RISK = "high_risk"
    SAFETY = "safety"
    ABUSE = "abuse"


@dataclass(frozen=True, slots=True)
class ExtractedField:
    key: str
    value: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.key.isidentifier() or not self.value.strip() or len(self.value) > 1000:
            raise ValueError("Extracted field is invalid")
        _confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class IntentResult:
    intent: Intent
    confidence: float
    entities: tuple[ExtractedField, ...]
    missing_information: tuple[str, ...]
    risk_flags: tuple[RiskFlag, ...]
    suggested_action: SuggestedAction
    rationale_category: str

    def __post_init__(self) -> None:
        _confidence(self.confidence)
        if not self.rationale_category.isidentifier() or len(self.rationale_category) > 100:
            raise ValueError("Intent rationale category is invalid")


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    fields: tuple[ExtractedField, ...]
    confidence: float

    def __post_init__(self) -> None:
        _confidence(self.confidence)
        if len({item.key for item in self.fields}) != len(self.fields):
            raise ValueError("Extracted field keys must be unique")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    label: str
    confidence: float
    rationale_category: str

    def __post_init__(self) -> None:
        _confidence(self.confidence)
        if not self.label.strip() or not self.rationale_category.isidentifier():
            raise ValueError("Classification result is invalid")


@dataclass(frozen=True, slots=True)
class RewriteResult:
    text: str
    confidence: float

    def __post_init__(self) -> None:
        _confidence(self.confidence)
        if not self.text.strip() or len(self.text) > 2000:
            raise ValueError("Rewrite result is invalid")


@dataclass(frozen=True, slots=True)
class SummaryResult:
    summary: str
    key_points: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        _confidence(self.confidence)
        if not self.summary.strip() or len(self.summary) > 2000:
            raise ValueError("Summary result is invalid")
        if len(self.key_points) > 10 or any(
            not item.strip() or len(item) > 500 for item in self.key_points
        ):
            raise ValueError("Summary key points are invalid")


AIResult = IntentResult | ExtractionResult | ClassificationResult | RewriteResult | SummaryResult


def _confidence(value: float) -> None:
    if isinstance(value, bool) or not 0 <= value <= 1:
        raise ValueError("AI confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    identifier: str
    version: int
    task: AITask
    template: str
    variables: frozenset[str]
    compatible_schemas: frozenset[str]
    metadata: Mapping[str, str] = field(default_factory=dict)
    deprecated: bool = False

    def __post_init__(self) -> None:
        if not self.identifier.replace("-", "_").isidentifier() or self.version < 1:
            raise ValueError("Prompt identity is invalid")
        if not self.template.strip() or not self.compatible_schemas:
            raise ValueError("Prompt text and compatibility are required")
        if any(not variable.isidentifier() for variable in self.variables):
            raise ValueError("Prompt variable names are invalid")
        discovered = {
            name for _, name, _, _ in Formatter().parse(self.template) if name is not None and name
        }
        if discovered != set(self.variables):
            raise ValueError("Prompt variables do not match the template")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def render(self, variables: Mapping[str, str]) -> str:
        if set(variables) != set(self.variables):
            raise ValueError("Prompt variables are incomplete or unexpected")
        rendered = self.template.format_map(dict(variables))
        if not rendered.strip() or len(rendered) > 20_000:
            raise ValueError("Rendered prompt is invalid")
        return rendered


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    task: AITask
    provider: str
    model: str
    prompt_id: str
    prompt_version: int
    schema_id: str
    temperature: float | None
    max_output_tokens: int
    timeout_seconds: float
    max_retries: int
    confidence_threshold: float
    structured_output_mode: str
    input_cost_per_million: Decimal = Decimal(0)
    output_cost_per_million: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip() or not self.schema_id.strip():
            raise ValueError("AI provider, model, and schema are required")
        if self.prompt_version < 1 or not 64 <= self.max_output_tokens <= 32_768:
            raise ValueError("AI prompt version or output limit is invalid")
        if not 0.01 <= self.timeout_seconds <= 120 or not 0 <= self.max_retries <= 5:
            raise ValueError("AI timeout or retry policy is invalid")
        _confidence(self.confidence_threshold)
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("AI temperature is invalid")
        if self.structured_output_mode != "strict_json_schema":
            raise ValueError("Only strict JSON schema output is supported")
        if self.input_cost_per_million < 0 or self.output_cost_per_million < 0:
            raise ValueError("AI model costs cannot be negative")


@dataclass(frozen=True, slots=True)
class AIRequest:
    tenant_id: TenantId
    conversation_id: ConversationId | None
    correlation_id: UUID
    task: AITask
    input_text: str
    prompt_variables: Mapping[str, str] = field(default_factory=dict)
    allowed_extraction_fields: frozenset[str] = frozenset()
    allowed_classification_labels: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.input_text.strip() or len(self.input_text) > 8000:
            raise ValueError("AI input must contain 1-8000 characters")
        if self.task is AITask.EXTRACTION and not self.allowed_extraction_fields:
            raise ValueError("Extraction requires an explicit field allowlist")
        if self.task is AITask.CLASSIFICATION and not self.allowed_classification_labels:
            raise ValueError("Classification requires an explicit label allowlist")
        if any(not key.isidentifier() for key in self.allowed_extraction_fields):
            raise ValueError("Extraction field allowlist is invalid")
        object.__setattr__(self, "prompt_variables", MappingProxyType(dict(self.prompt_variables)))


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    task: AITask
    model: str
    system_prompt: str
    user_input: str
    schema_name: str
    json_schema: Mapping[str, Any]
    temperature: float | None
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    provider: str
    model: str
    output: Mapping[str, Any]
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Provider token usage cannot be negative")


@dataclass(frozen=True, slots=True)
class AIExecution:
    status: AICompletionStatus
    result: AIResult
    failure_code: AIFailureCode | None
    attempts: int


@dataclass(frozen=True, slots=True)
class AIOperationRecord:
    operation_id: UUID
    tenant_id: TenantId
    conversation_id: ConversationId | None
    correlation_id: UUID
    task: AITask
    provider: str
    model: str
    prompt_id: str
    prompt_version: int
    schema_id: str
    status: AICompletionStatus
    attempts: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    failure_code: AIFailureCode | None
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("AI operation time must be timezone-aware")
        if self.attempts < 0 or self.latency_ms < 0:
            raise ValueError("AI operation attempts and latency cannot be negative")
        if self.input_tokens < 0 or self.output_tokens < 0 or self.estimated_cost < 0:
            raise ValueError("AI operation usage cannot be negative")
