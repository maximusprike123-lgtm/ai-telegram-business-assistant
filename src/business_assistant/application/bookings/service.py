"""Identity-scoped Phase 5 booking use cases."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from business_assistant.application.common.ports import Clock
from business_assistant.application.common.security import Permission, Principal
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.shared import BookingDraftId, BookingId, ServiceId

from .engine import calculate_availability
from .models import AvailableSlot, BookingDraft, BookingResult, SlotHold
from .ports import BookingStore


class BookingApplication:
    def __init__(self, store: BookingStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def availability(
        self, principal: Principal, service_id: ServiceId, local_date: date
    ) -> tuple[AvailableSlot, ...]:
        principal.require(Permission.BOOKING_READ)
        now = self._clock.now()
        context = await self._store.availability_context(principal.tenant_id, service_id, now=now)
        if context is None:
            return ()
        return calculate_availability(context, local_date=local_date, now=now)

    async def start(self, identity: TelegramIdentity, service_id: ServiceId) -> BookingDraft:
        return await self._store.start_draft(
            identity.tenant_id,
            identity.customer_id,
            identity.conversation_id,
            service_id,
            now=self._clock.now(),
        )

    async def dates(
        self, identity: TelegramIdentity, draft: BookingDraft, *, days: int = 7
    ) -> tuple[date, ...]:
        now = self._clock.now()
        context = await self._store.availability_context(
            identity.tenant_id, draft.service_id, now=now
        )
        if context is None or not context.resources:
            return ()
        today = now.astimezone(ZoneInfo(context.resources[0].schedule.timezone)).date()
        horizon_date = (
            (now + context.policy.booking_horizon)
            .astimezone(ZoneInfo(context.resources[0].schedule.timezone))
            .date()
        )
        found: list[date] = []
        candidate = today
        while candidate <= horizon_date and len(found) < days:
            if calculate_availability(context, local_date=candidate, now=now):
                found.append(candidate)
            candidate += timedelta(days=1)
        return tuple(found)

    async def active(self, identity: TelegramIdentity) -> BookingDraft | None:
        return await self._store.get_active_draft(
            identity.tenant_id,
            identity.customer_id,
            identity.conversation_id,
            now=self._clock.now(),
        )

    async def choose_date(
        self, identity: TelegramIdentity, draft_id: BookingDraftId, selected_date: date
    ) -> tuple[BookingDraft, tuple[AvailableSlot, ...]]:
        now = self._clock.now()
        draft = await self._store.select_date(
            identity.tenant_id, identity.customer_id, draft_id, selected_date, now=now
        )
        context = await self._store.availability_context(
            identity.tenant_id, draft.service_id, now=now
        )
        slots = (
            ()
            if context is None
            else calculate_availability(context, local_date=selected_date, now=now)
        )
        return draft, slots

    async def hold(
        self,
        identity: TelegramIdentity,
        draft_id: BookingDraftId,
        slot_index: int,
        idempotency_key: str,
    ) -> SlotHold:
        return await self._store.create_hold(
            identity.tenant_id,
            identity.customer_id,
            draft_id,
            slot_index=slot_index,
            idempotency_key=idempotency_key,
            now=self._clock.now(),
        )

    async def contact(
        self,
        identity: TelegramIdentity,
        draft_id: BookingDraftId,
        *,
        name: str | None = None,
        phone: str | None = None,
        note: str | None = None,
    ) -> BookingDraft:
        return await self._store.update_contact(
            identity.tenant_id,
            identity.customer_id,
            draft_id,
            name=name,
            phone=phone,
            note=note,
            now=self._clock.now(),
        )

    async def current_hold(
        self, identity: TelegramIdentity, draft_id: BookingDraftId
    ) -> SlotHold | None:
        return await self._store.get_hold(
            identity.tenant_id, identity.customer_id, draft_id, now=self._clock.now()
        )

    async def abandon(self, identity: TelegramIdentity) -> bool:
        return await self._store.cancel_draft(
            identity.tenant_id,
            identity.customer_id,
            identity.conversation_id,
            now=self._clock.now(),
        )

    async def confirm(
        self, identity: TelegramIdentity, draft_id: BookingDraftId, idempotency_key: str
    ) -> BookingResult:
        return await self._store.confirm(
            identity.tenant_id,
            identity.customer_id,
            draft_id,
            idempotency_key=idempotency_key,
            now=self._clock.now(),
        )

    async def latest(self, identity: TelegramIdentity) -> BookingResult | None:
        return await self._store.latest_booking(
            identity.tenant_id, identity.customer_id, now=self._clock.now()
        )

    async def get(self, identity: TelegramIdentity, booking_id: BookingId) -> BookingResult | None:
        return await self._store.get_booking(identity.tenant_id, identity.customer_id, booking_id)

    async def start_reschedule(
        self, identity: TelegramIdentity, booking_id: BookingId
    ) -> BookingDraft:
        booking = await self._store.get_booking(
            identity.tenant_id, identity.customer_id, booking_id
        )
        if booking is None or booking.status != "confirmed":
            from business_assistant.application.common.errors import BookingNotFoundError

            raise BookingNotFoundError()
        return await self._store.start_draft(
            identity.tenant_id,
            identity.customer_id,
            identity.conversation_id,
            booking.service_id,
            now=self._clock.now(),
            reschedule_booking_id=booking.id,
        )

    async def cancel(self, identity: TelegramIdentity, booking_id: BookingId) -> BookingResult:
        return await self._store.cancel_booking(
            identity.tenant_id, identity.customer_id, booking_id, now=self._clock.now()
        )
