"""Framework-independent contracts for consent and lead qualification."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from business_assistant.domain.shared import (
    ConversationId,
    CustomerId,
    LeadId,
    QualificationSchemaId,
    QualificationSessionId,
    TenantId,
)

Answer = str | int | Decimal | bool | date | tuple[str, ...]


class QualificationFieldType(StrEnum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    PHONE = "phone"
    EMAIL = "email"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


class MatchOperator(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"


class QualificationSessionStatus(StrEnum):
    AWAITING_CONSENT = "awaiting_consent"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ConsentDecision(StrEnum):
    ACCEPTED = "accepted"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class FieldValidation:
    min_length: int | None = None
    max_length: int | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    options: tuple[str, ...] = ()
    pattern: str | None = None

    def __post_init__(self) -> None:
        if self.min_length is not None and self.min_length < 0:
            raise ValueError("Minimum length cannot be negative")
        if self.max_length is not None and self.max_length < 1:
            raise ValueError("Maximum length must be positive")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("Minimum length cannot exceed maximum length")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum value cannot exceed maximum value")
        if len(set(self.options)) != len(self.options) or any(
            not item.strip() for item in self.options
        ):
            raise ValueError("Field options must be unique and non-blank")


@dataclass(frozen=True, slots=True)
class ScoreRule:
    code: str
    operator: MatchOperator
    expected: str | int | Decimal | bool
    points: int

    def __post_init__(self) -> None:
        if not self.code.strip() or not -100 <= self.points <= 100:
            raise ValueError("Score rule code and points are invalid")


@dataclass(frozen=True, slots=True)
class HandoffTrigger:
    code: str
    operator: MatchOperator
    expected: str | int | Decimal | bool
    reason_code: str
    priority: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.reason_code.strip():
            raise ValueError("Handoff trigger identity is required")
        if self.priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("Handoff trigger priority is invalid")


@dataclass(frozen=True, slots=True)
class QualificationField:
    key: str
    label: str
    prompt: str
    field_type: QualificationFieldType
    validation: FieldValidation
    required: bool
    order: int
    sensitivity: Sensitivity
    score_rules: tuple[ScoreRule, ...] = ()
    handoff_triggers: tuple[HandoffTrigger, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.isidentifier() or not self.label.strip() or not self.prompt.strip():
            raise ValueError("Qualification field identity and copy are invalid")
        if self.order < 0:
            raise ValueError("Qualification field order cannot be negative")
        choice = self.field_type in {
            QualificationFieldType.SINGLE_CHOICE,
            QualificationFieldType.MULTI_CHOICE,
        }
        if choice != bool(self.validation.options):
            raise ValueError("Only choice fields require options")


@dataclass(frozen=True, slots=True)
class GradeBand:
    minimum_score: int
    grade: str

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_score <= 100 or not self.grade.strip():
            raise ValueError("Grade band is invalid")


@dataclass(frozen=True, slots=True)
class QualificationSchema:
    id: QualificationSchemaId
    tenant_id: TenantId
    code: str
    version: int
    title: str
    consent_version: str
    consent_purpose: str
    fields: tuple[QualificationField, ...]
    grade_bands: tuple[GradeBand, ...]
    session_ttl: timedelta
    handoff_response_minutes: int
    published: bool
    active: bool

    def __post_init__(self) -> None:
        if not self.code.strip() or self.version < 1 or not self.title.strip():
            raise ValueError("Qualification schema identity is invalid")
        if not self.consent_version.strip() or not self.consent_purpose.strip():
            raise ValueError("Qualification consent policy is required")
        if not self.fields or self.session_ttl <= timedelta(0):
            raise ValueError("Qualification fields and a positive session TTL are required")
        keys = [item.key for item in self.fields]
        orders = [item.order for item in self.fields]
        if len(set(keys)) != len(keys) or len(set(orders)) != len(orders):
            raise ValueError("Qualification field keys and order must be unique")
        if tuple(sorted(self.fields, key=lambda item: item.order)) != self.fields:
            raise ValueError("Qualification fields must be stored in order")
        if not self.grade_bands or self.grade_bands[0].minimum_score != 0:
            raise ValueError("Qualification grades must start at score zero")
        if tuple(sorted(self.grade_bands, key=lambda item: item.minimum_score)) != self.grade_bands:
            raise ValueError("Qualification grade bands must be ordered")
        if not 1 <= self.handoff_response_minutes <= 10_080:
            raise ValueError("Handoff response time is invalid")


@dataclass(frozen=True, slots=True)
class QualificationSession:
    id: QualificationSessionId
    tenant_id: TenantId
    customer_id: CustomerId
    conversation_id: ConversationId
    schema_id: QualificationSchemaId
    schema_code: str
    schema_version: int
    status: QualificationSessionStatus
    answers: dict[str, Answer] = field(default_factory=dict)
    current_field_key: str | None = None
    expires_at: datetime | None = None
    consent_decision: ConsentDecision | None = None
    consent_at: datetime | None = None
    lead_id: LeadId | None = None


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    grade: str
    matched_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TriggerResult:
    reason_code: str
    priority: str
    matched_rules: tuple[str, ...]
