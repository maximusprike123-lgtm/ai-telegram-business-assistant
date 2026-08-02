from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..shared import (
    ConversationId,
    HandoffId,
    InvalidStateTransition,
    TenantId,
    ValidationError,
    ensure_aware,
)


class HandoffStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


class HandoffPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


_TRANSITIONS: dict[HandoffStatus, frozenset[HandoffStatus]] = {
    HandoffStatus.QUEUED: frozenset({HandoffStatus.CLAIMED, HandoffStatus.CANCELLED}),
    HandoffStatus.CLAIMED: frozenset({HandoffStatus.RESOLVED, HandoffStatus.CANCELLED}),
    HandoffStatus.RESOLVED: frozenset({HandoffStatus.REOPENED}),
    HandoffStatus.REOPENED: frozenset({HandoffStatus.QUEUED}),
    HandoffStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class HandoffCase:
    id: HandoffId
    tenant_id: TenantId
    conversation_id: ConversationId
    reason_code: str
    priority: HandoffPriority
    summary: str
    response_due_at: datetime
    status: HandoffStatus = HandoffStatus.QUEUED
    assignee_id: str | None = None

    def __post_init__(self) -> None:
        if not self.reason_code.strip() or not self.summary.strip():
            raise ValidationError("Handoff reason and summary are required")
        ensure_aware(self.response_due_at, "response_due_at")
        if self.status is HandoffStatus.CLAIMED and not self.assignee_id:
            raise ValidationError("A claimed handoff requires an assignee")

    def transition_to(self, target: HandoffStatus, *, assignee_id: str | None = None) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition("Handoff", self.status, target)
        if target is HandoffStatus.CLAIMED:
            if not assignee_id or not assignee_id.strip():
                raise ValidationError("Claiming a handoff requires an assignee")
            self.assignee_id = assignee_id
        elif target in {HandoffStatus.REOPENED, HandoffStatus.QUEUED}:
            self.assignee_id = None
        self.status = target
