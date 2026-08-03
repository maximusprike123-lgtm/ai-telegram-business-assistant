"""Phase 5 persistence port; implementations own their PostgreSQL transactions."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from business_assistant.domain.shared import (
    BookingDraftId,
    BookingId,
    ConversationId,
    CustomerId,
    ServiceId,
    TenantId,
)

from .models import (
    AvailabilityContext,
    BookingDraft,
    BookingResult,
    SlotHold,
)


class BookingStore(Protocol):
    async def availability_context(
        self, tenant_id: TenantId, service_id: ServiceId, *, now: datetime
    ) -> AvailabilityContext | None: ...

    async def start_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        service_id: ServiceId,
        *,
        now: datetime,
        reschedule_booking_id: BookingId | None = None,
    ) -> BookingDraft: ...

    async def get_active_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        *,
        now: datetime,
    ) -> BookingDraft | None: ...

    async def select_date(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        selected_date: date,
        *,
        now: datetime,
    ) -> BookingDraft: ...

    async def create_hold(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        slot_index: int,
        idempotency_key: str,
        now: datetime,
    ) -> SlotHold: ...

    async def update_contact(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        name: str | None,
        phone: str | None,
        note: str | None,
        now: datetime,
    ) -> BookingDraft: ...

    async def get_hold(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        now: datetime,
    ) -> SlotHold | None: ...

    async def cancel_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        *,
        now: datetime,
    ) -> bool: ...

    async def confirm(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        idempotency_key: str,
        now: datetime,
    ) -> BookingResult: ...

    async def latest_booking(
        self, tenant_id: TenantId, customer_id: CustomerId, *, now: datetime
    ) -> BookingResult | None: ...

    async def get_booking(
        self, tenant_id: TenantId, customer_id: CustomerId, booking_id: BookingId
    ) -> BookingResult | None: ...

    async def cancel_booking(
        self, tenant_id: TenantId, customer_id: CustomerId, booking_id: BookingId, *, now: datetime
    ) -> BookingResult: ...

    async def expire_holds(self, *, now: datetime, limit: int) -> int: ...

    async def booking_history(
        self, tenant_id: TenantId, customer_id: CustomerId, booking_id: BookingId
    ) -> Sequence[tuple[str, str, datetime]]: ...
