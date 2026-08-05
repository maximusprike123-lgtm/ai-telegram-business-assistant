"""Provider-neutral models for reliable background delivery."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from business_assistant.domain.shared import TenantId


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"


@dataclass(frozen=True, slots=True)
class NotificationSubscription:
    id: UUID
    tenant_id: TenantId
    channel: NotificationChannel
    recipient_id: str
    event_types: frozenset[str]
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.recipient_id.isdecimal() or not self.event_types:
            raise ValueError("Notification subscription is invalid")
        if any(not item or len(item) > 100 for item in self.event_types):
            raise ValueError("Notification event type is invalid")


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    id: UUID
    tenant_id: TenantId
    event_type: str
    channel: NotificationChannel
    recipient_id: str
    payload: dict[str, object]
    attempts: int


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    claimed: int
    succeeded: int
    retried: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 6
    base_delay_seconds: int = 5
    maximum_delay_seconds: int = 900

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 20:
            raise ValueError("Maximum attempts must be between 1 and 20")
        if not 1 <= self.base_delay_seconds <= self.maximum_delay_seconds:
            raise ValueError("Retry delay policy is invalid")

    def next_attempt_at(self, *, claim_id: UUID, attempts: int, now: datetime) -> datetime:
        exponent = max(0, attempts - 1)
        delay = min(self.maximum_delay_seconds, self.base_delay_seconds * (2**exponent))
        # Stable jitter avoids retry synchronization without introducing nondeterministic tests.
        jitter = claim_id.int % max(1, min(delay, 17))
        return now + timedelta(seconds=min(self.maximum_delay_seconds, delay + jitter))


@dataclass(frozen=True, slots=True)
class WorkerHealth:
    pending_outbox: int
    pending_notifications: int
    processing_notifications: int
    dead_letters: int
    oldest_due_at: datetime | None
    last_success_at: datetime | None
