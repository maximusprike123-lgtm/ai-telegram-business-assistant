"""Framework-independent Phase 5 booking data contracts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import (
    BookingDraftId,
    BookingId,
    ConversationId,
    CustomerId,
    ResourceId,
    ServiceId,
    SlotHoldId,
    TenantId,
    TimeRange,
)


class DraftStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CONFIRMED = "confirmed"


class HoldStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class BookingPolicy:
    slot_interval: timedelta
    booking_horizon: timedelta
    minimum_notice: timedelta
    hold_duration: timedelta
    draft_duration: timedelta
    change_cutoff: timedelta
    customer_name_max_length: int
    customer_phone_max_length: int
    customer_note_max_length: int

    def __post_init__(self) -> None:
        positive = (
            self.slot_interval,
            self.booking_horizon,
            self.minimum_notice,
            self.hold_duration,
            self.draft_duration,
        )
        if any(value <= timedelta(0) for value in positive):
            raise ValueError("Booking policy durations must be positive")
        if self.change_cutoff < timedelta(0):
            raise ValueError("Booking change cutoff cannot be negative")
        if not 1 <= self.customer_name_max_length <= 200:
            raise ValueError("Customer name limit is invalid")
        if not 8 <= self.customer_phone_max_length <= 32:
            raise ValueError("Customer phone limit is invalid")
        if not 0 <= self.customer_note_max_length <= 2000:
            raise ValueError("Customer note limit is invalid")


@dataclass(frozen=True, slots=True)
class BusyPeriod:
    time_range: TimeRange
    capacity_used: int = 1


@dataclass(frozen=True, slots=True)
class AvailableResource:
    id: ResourceId
    schedule: BusinessSchedule
    capacity: int
    active: bool
    busy_periods: tuple[BusyPeriod, ...] = ()


@dataclass(frozen=True, slots=True)
class AvailabilityContext:
    tenant_id: TenantId
    service_id: ServiceId
    service_name: str
    duration: timedelta
    cleanup_buffer: timedelta
    active: bool
    bookable: bool
    policy: BookingPolicy
    resources: tuple[AvailableResource, ...]


@dataclass(frozen=True, slots=True)
class AvailableSlot:
    start_at: datetime
    end_at: datetime
    resource_id: ResourceId
    local_date: date
    local_time: str
    timezone: str


@dataclass(frozen=True, slots=True)
class BookingDraft:
    id: BookingDraftId
    tenant_id: TenantId
    customer_id: CustomerId
    conversation_id: ConversationId
    service_id: ServiceId
    selected_date: date | None
    hold_id: SlotHoldId | None
    customer_name: str | None
    customer_phone: str | None
    customer_note: str | None
    status: DraftStatus
    expires_at: datetime
    reschedule_booking_id: BookingId | None = None


@dataclass(frozen=True, slots=True)
class SlotHold:
    id: SlotHoldId
    tenant_id: TenantId
    customer_id: CustomerId
    conversation_id: ConversationId
    draft_id: BookingDraftId
    service_id: ServiceId
    resource_id: ResourceId
    time_range: TimeRange
    expires_at: datetime
    status: HoldStatus
    timezone: str


@dataclass(frozen=True, slots=True)
class BookingResult:
    id: BookingId
    service_id: ServiceId
    public_reference: str
    service_name: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
