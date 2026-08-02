from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from ..shared import (
    BookingId,
    CustomerId,
    IdempotencyKey,
    InvalidStateTransition,
    ServiceId,
    TenantId,
    TenantMismatchError,
    TimeRange,
    ValidationError,
)


class BookingStatus(StrEnum):
    DRAFT = "draft"
    HELD = "held"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULE_PENDING = "reschedule_pending"
    EXPIRED = "expired"


_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.DRAFT: frozenset({BookingStatus.HELD}),
    BookingStatus.HELD: frozenset({BookingStatus.CONFIRMED, BookingStatus.EXPIRED}),
    BookingStatus.CONFIRMED: frozenset(
        {
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
            BookingStatus.RESCHEDULE_PENDING,
        }
    ),
    BookingStatus.RESCHEDULE_PENDING: frozenset({BookingStatus.CONFIRMED, BookingStatus.CANCELLED}),
    BookingStatus.COMPLETED: frozenset(),
    BookingStatus.CANCELLED: frozenset(),
    BookingStatus.NO_SHOW: frozenset(),
    BookingStatus.EXPIRED: frozenset(),
}


@dataclass(slots=True)
class Booking:
    id: BookingId
    tenant_id: TenantId
    customer_id: CustomerId
    service_id: ServiceId
    time_range: TimeRange
    idempotency_key: IdempotencyKey
    service_snapshot: Mapping[str, Any]
    customer_snapshot: Mapping[str, Any]
    status: BookingStatus = BookingStatus.DRAFT
    history: list[tuple[BookingStatus, BookingStatus, str | None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.service_snapshot or not self.customer_snapshot:
            raise ValidationError("Booking requires immutable service and customer snapshots")
        self.service_snapshot = MappingProxyType(dict(self.service_snapshot))
        self.customer_snapshot = MappingProxyType(dict(self.customer_snapshot))

    def assert_same_tenant(self, related_tenant_id: TenantId, relationship: str) -> None:
        if related_tenant_id != self.tenant_id:
            raise TenantMismatchError(relationship)

    def transition_to(self, target: BookingStatus, *, reason: str | None = None) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition("Booking", self.status, target)
        previous = self.status
        self.status = target
        self.history.append((previous, target, reason))
