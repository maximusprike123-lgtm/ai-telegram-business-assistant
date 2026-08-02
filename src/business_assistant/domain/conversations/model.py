from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..shared import (
    ConversationId,
    CustomerId,
    InvalidStateTransition,
    Locale,
    TenantId,
    ensure_aware,
)


class ConversationStatus(StrEnum):
    ACTIVE_BOT = "active_bot"
    HANDOFF_QUEUED = "handoff_queued"
    HUMAN_ACTIVE = "human_active"
    CLOSED = "closed"


_TRANSITIONS: dict[ConversationStatus, frozenset[ConversationStatus]] = {
    ConversationStatus.ACTIVE_BOT: frozenset(
        {ConversationStatus.HANDOFF_QUEUED, ConversationStatus.CLOSED}
    ),
    ConversationStatus.HANDOFF_QUEUED: frozenset(
        {ConversationStatus.HUMAN_ACTIVE, ConversationStatus.ACTIVE_BOT, ConversationStatus.CLOSED}
    ),
    ConversationStatus.HUMAN_ACTIVE: frozenset(
        {ConversationStatus.ACTIVE_BOT, ConversationStatus.CLOSED}
    ),
    ConversationStatus.CLOSED: frozenset(),
}


@dataclass(slots=True)
class Conversation:
    id: ConversationId
    tenant_id: TenantId
    customer_id: CustomerId
    locale: Locale
    status: ConversationStatus = ConversationStatus.ACTIVE_BOT
    active_workflow: str | None = None
    last_message_at: datetime | None = None

    def transition_to(self, target: ConversationStatus) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition("Conversation", self.status, target)
        self.status = target
        if target is not ConversationStatus.ACTIVE_BOT:
            self.active_workflow = None

    def touch(self, at: datetime) -> None:
        self.last_message_at = ensure_aware(at, "last_message_at")

    @property
    def generative_replies_allowed(self) -> bool:
        return self.status is ConversationStatus.ACTIVE_BOT
