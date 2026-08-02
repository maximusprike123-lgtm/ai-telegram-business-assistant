from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from ..shared import (
    ConversationId,
    CustomerId,
    InvalidStateTransition,
    LeadId,
    TenantId,
    ValidationError,
    ensure_aware,
)


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    UNQUALIFIED = "unqualified"
    CLOSED = "closed"


class LeadPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset({LeadStatus.QUALIFYING, LeadStatus.UNQUALIFIED, LeadStatus.CLOSED}),
    LeadStatus.QUALIFYING: frozenset(
        {LeadStatus.QUALIFIED, LeadStatus.UNQUALIFIED, LeadStatus.CLOSED}
    ),
    LeadStatus.QUALIFIED: frozenset({LeadStatus.CONTACTED, LeadStatus.CLOSED}),
    LeadStatus.CONTACTED: frozenset({LeadStatus.CONVERTED, LeadStatus.CLOSED}),
    LeadStatus.CONVERTED: frozenset({LeadStatus.CLOSED}),
    LeadStatus.UNQUALIFIED: frozenset({LeadStatus.QUALIFYING, LeadStatus.CLOSED}),
    LeadStatus.CLOSED: frozenset({LeadStatus.QUALIFYING}),
}


@dataclass(slots=True)
class Lead:
    id: LeadId
    tenant_id: TenantId
    customer_id: CustomerId
    conversation_id: ConversationId
    schema_code: str
    schema_version: int
    source: str
    answers: dict[str, Any] = field(default_factory=dict)
    status: LeadStatus = LeadStatus.NEW
    score: int | None = None
    priority: LeadPriority | None = None
    score_explanation: Mapping[str, Any] | None = None
    consent_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.schema_code.strip() or self.schema_version < 1 or not self.source.strip():
            raise ValidationError("Lead schema identity and source are required")
        if self.consent_at is not None:
            ensure_aware(self.consent_at, "consent_at")
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValidationError("Lead score must be between 0 and 100")

    def transition_to(self, target: LeadStatus) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition("Lead", self.status, target)
        self.status = target

    def record_answer(self, key: str, value: Any) -> None:
        if self.status not in {LeadStatus.NEW, LeadStatus.QUALIFYING}:
            raise ValidationError("Lead answers can only change while qualifying")
        if not key.strip():
            raise ValidationError("Lead answer key cannot be blank")
        self.answers[key] = value

    def apply_deterministic_score(
        self,
        score: int,
        priority: LeadPriority,
        explanation: Mapping[str, Any],
    ) -> None:
        if not 0 <= score <= 100:
            raise ValidationError("Lead score must be between 0 and 100")
        if not explanation:
            raise ValidationError("Lead score requires an explanation")
        self.score = score
        self.priority = priority
        self.score_explanation = MappingProxyType(dict(explanation))

    def grant_consent(self, at: datetime) -> None:
        self.consent_at = ensure_aware(at, "consent_at")

    def qualify(self) -> None:
        if self.consent_at is None or self.score is None or self.priority is None:
            raise ValidationError(
                "Lead requires consent and deterministic scoring before qualification"
            )
        self.transition_to(LeadStatus.QUALIFIED)
