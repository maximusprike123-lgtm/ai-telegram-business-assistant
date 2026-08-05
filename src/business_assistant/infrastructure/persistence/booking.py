"""PostgreSQL implementation of transactional Phase 5 booking operations."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.bookings import (
    AvailabilityContext,
    AvailableResource,
    BookingDraft,
    BookingPolicy,
    BookingResult,
    BusyPeriod,
    DraftStatus,
    HoldStatus,
    SlotHold,
    calculate_availability,
)
from business_assistant.application.common.errors import (
    BookingConflictError,
    BookingExpiredError,
    BookingNotFoundError,
    BookingPolicyError,
)
from business_assistant.application.observability import current_correlation_id
from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import (
    BookingDraftId,
    BookingId,
    ConversationId,
    CustomerId,
    PhoneNumber,
    ResourceId,
    ServiceId,
    SlotHoldId,
    TenantId,
    TimeRange,
    ValidationError,
)

from .sqlalchemy.mappers import schedule_from_rows
from .sqlalchemy.models import (
    BookingDraftRow,
    BookingPolicyRow,
    BookingRow,
    BookingStatusHistoryRow,
    BusinessScheduleRow,
    ConversationRow,
    OutboxEventRow,
    ResourceRow,
    ResourceUnavailabilityRow,
    ScheduleIntervalRow,
    ScheduleOverrideRow,
    ServiceResourceRow,
    ServiceRow,
    SlotHoldRow,
    TenantEntitlementRow,
    TenantRow,
)


def _booking_event(
    session: AsyncSession,
    tenant_id: TenantId,
    booking: BookingRow,
    event_type: str,
    key: str,
    now: datetime,
) -> None:
    event_id = uuid5(NAMESPACE_URL, f"business-assistant:{tenant_id}:{key}")
    session.add(
        OutboxEventRow(
            id=event_id,
            event_id=event_id,
            correlation_id=current_correlation_id(),
            tenant_id=tenant_id.value,
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type=event_type,
            event_version=1,
            payload={
                "booking_id": str(booking.id),
                "public_reference": booking.public_reference,
                "service_id": str(booking.service_id),
                "start_at": booking.start_at.isoformat(),
            },
            status="pending",
            attempts=0,
            available_at=now,
            occurred_at=now,
        )
    )


def _policy(row: BookingPolicyRow) -> BookingPolicy:
    return BookingPolicy(
        timedelta(minutes=row.slot_interval_minutes),
        timedelta(days=row.booking_horizon_days),
        timedelta(minutes=row.minimum_notice_minutes),
        timedelta(minutes=row.hold_duration_minutes),
        timedelta(minutes=row.draft_expiry_minutes),
        timedelta(minutes=row.change_cutoff_minutes),
        row.customer_name_max_length,
        row.customer_phone_max_length,
        row.customer_note_max_length,
    )


def _draft(row: BookingDraftRow) -> BookingDraft:
    return BookingDraft(
        BookingDraftId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id),
        ConversationId(row.conversation_id),
        ServiceId(row.service_id),
        row.selected_date,
        SlotHoldId(row.hold_id) if row.hold_id else None,
        row.customer_name,
        row.customer_phone,
        row.customer_note,
        DraftStatus(row.status),
        row.expires_at,
        BookingId(row.reschedule_booking_id) if row.reschedule_booking_id else None,
    )


def _hold(row: SlotHoldRow) -> SlotHold:
    return SlotHold(
        SlotHoldId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id),
        ConversationId(row.conversation_id),
        BookingDraftId(row.draft_id),
        ServiceId(row.service_id),
        ResourceId(row.resource_id),
        TimeRange(row.start_at, row.end_at),
        row.expires_at,
        HoldStatus(row.status),
        row.timezone,
    )


class SQLAlchemyBookingStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _availability_context(
        self, session: AsyncSession, tenant_id: TenantId, service_id: ServiceId, *, now: datetime
    ) -> AvailabilityContext | None:
        result = (
            await session.execute(
                select(ServiceRow, BookingPolicyRow)
                .join(BookingPolicyRow, BookingPolicyRow.tenant_id == ServiceRow.tenant_id)
                .where(
                    ServiceRow.tenant_id == tenant_id.value,
                    ServiceRow.id == service_id.value,
                )
            )
        ).one_or_none()
        if result is None:
            return None
        service, policy_row = result
        resource_rows = list(
            (
                await session.scalars(
                    select(ResourceRow)
                    .join(
                        ServiceResourceRow,
                        (ServiceResourceRow.tenant_id == ResourceRow.tenant_id)
                        & (ServiceResourceRow.resource_id == ResourceRow.id),
                    )
                    .where(
                        ResourceRow.tenant_id == tenant_id.value,
                        ServiceResourceRow.service_id == service_id.value,
                        ServiceResourceRow.active.is_(True),
                    )
                    .order_by(ResourceRow.id)
                )
            ).all()
        )
        if not resource_rows:
            return AvailabilityContext(
                tenant_id,
                service_id,
                str(service.names.get("en", service.code)),
                timedelta(seconds=service.duration_seconds),
                timedelta(seconds=service.buffer_seconds),
                service.active,
                service.bookable,
                _policy(policy_row),
                (),
            )
        schedule_ids = {row.schedule_id for row in resource_rows}
        schedules = list(
            (
                await session.scalars(
                    select(BusinessScheduleRow).where(
                        BusinessScheduleRow.tenant_id == tenant_id.value,
                        BusinessScheduleRow.id.in_(schedule_ids),
                    )
                )
            ).all()
        )
        intervals = list(
            (
                await session.scalars(
                    select(ScheduleIntervalRow).where(
                        ScheduleIntervalRow.tenant_id == tenant_id.value,
                        ScheduleIntervalRow.schedule_id.in_(schedule_ids),
                    )
                )
            ).all()
        )
        overrides = list(
            (
                await session.scalars(
                    select(ScheduleOverrideRow).where(
                        ScheduleOverrideRow.tenant_id == tenant_id.value,
                        ScheduleOverrideRow.schedule_id.in_(schedule_ids),
                    )
                )
            ).all()
        )
        schedule_map: dict[UUID, BusinessSchedule] = {}
        for schedule in schedules:
            schedule_map[schedule.id] = schedule_from_rows(
                schedule,
                [item for item in intervals if item.schedule_id == schedule.id],
                [item for item in overrides if item.schedule_id == schedule.id],
            )
        resource_ids = [row.id for row in resource_rows]
        horizon_end = now + timedelta(days=policy_row.booking_horizon_days + 1)
        booking_rows = list(
            (
                await session.execute(
                    select(BookingRow, ServiceRow.buffer_seconds)
                    .join(
                        ServiceRow,
                        (ServiceRow.tenant_id == BookingRow.tenant_id)
                        & (ServiceRow.id == BookingRow.service_id),
                    )
                    .where(
                        BookingRow.tenant_id == tenant_id.value,
                        BookingRow.resource_id.in_(resource_ids),
                        BookingRow.status.in_(("confirmed", "reschedule_pending")),
                        BookingRow.end_at > now,
                        BookingRow.start_at < horizon_end,
                    )
                )
            ).all()
        )
        hold_rows = list(
            (
                await session.scalars(
                    select(SlotHoldRow).where(
                        SlotHoldRow.tenant_id == tenant_id.value,
                        SlotHoldRow.resource_id.in_(resource_ids),
                        SlotHoldRow.status == "active",
                        SlotHoldRow.expires_at > now,
                        SlotHoldRow.end_at > now,
                        SlotHoldRow.start_at < horizon_end,
                    )
                )
            ).all()
        )
        unavailable_rows = list(
            (
                await session.scalars(
                    select(ResourceUnavailabilityRow).where(
                        ResourceUnavailabilityRow.tenant_id == tenant_id.value,
                        ResourceUnavailabilityRow.resource_id.in_(resource_ids),
                        ResourceUnavailabilityRow.active.is_(True),
                        ResourceUnavailabilityRow.end_at > now,
                        ResourceUnavailabilityRow.start_at < horizon_end,
                    )
                )
            ).all()
        )
        busy: dict[UUID, list[BusyPeriod]] = defaultdict(list)
        for booking, buffer_seconds in booking_rows:
            assert booking.resource_id is not None
            busy[booking.resource_id].append(
                BusyPeriod(
                    TimeRange(
                        booking.start_at,
                        booking.end_at + timedelta(seconds=buffer_seconds),
                    )
                )
            )
        for hold in hold_rows:
            busy[hold.resource_id].append(BusyPeriod(TimeRange(hold.start_at, hold.end_at)))
        capacity_by_id = {row.id: row.capacity for row in resource_rows}
        for unavailable in unavailable_rows:
            busy[unavailable.resource_id].append(
                BusyPeriod(
                    TimeRange(unavailable.start_at, unavailable.end_at),
                    capacity_by_id[unavailable.resource_id],
                )
            )
        resources = tuple(
            AvailableResource(
                ResourceId(row.id),
                schedule_map[row.schedule_id],
                row.capacity,
                row.active,
                tuple(sorted(busy[row.id], key=lambda item: item.time_range.start)),
            )
            for row in resource_rows
            if row.schedule_id in schedule_map
        )
        return AvailabilityContext(
            tenant_id,
            service_id,
            str(service.names.get("en", service.code)),
            timedelta(seconds=service.duration_seconds),
            timedelta(seconds=service.buffer_seconds),
            service.active,
            service.bookable,
            _policy(policy_row),
            resources,
        )

    async def availability_context(
        self, tenant_id: TenantId, service_id: ServiceId, *, now: datetime
    ) -> AvailabilityContext | None:
        async with self._session_factory() as session:
            return await self._availability_context(session, tenant_id, service_id, now=now)

    @staticmethod
    async def _identity_lock(
        session: AsyncSession, tenant_id: TenantId, customer_id: CustomerId
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"booking-identity:{tenant_id}:{customer_id}"},
        )

    @staticmethod
    async def _resource_lock(
        session: AsyncSession, tenant_id: TenantId, resource_id: ResourceId
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"booking-resource:{tenant_id}:{resource_id}"},
        )

    async def start_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        service_id: ServiceId,
        *,
        now: datetime,
        reschedule_booking_id: BookingId | None = None,
    ) -> BookingDraft:
        async with self._session_factory() as session, session.begin():
            await self._identity_lock(session, tenant_id, customer_id)
            context = await self._availability_context(session, tenant_id, service_id, now=now)
            if (
                context is None
                or not context.active
                or not context.bookable
                or not context.resources
            ):
                raise BookingPolicyError("This service is not available for booking")
            if reschedule_booking_id is not None:
                original = await session.scalar(
                    select(BookingRow).where(
                        BookingRow.tenant_id == tenant_id.value,
                        BookingRow.customer_id == customer_id.value,
                        BookingRow.id == reschedule_booking_id.value,
                        BookingRow.status == "confirmed",
                    )
                )
                if original is None or original.service_id != service_id.value:
                    raise BookingNotFoundError()
            await session.execute(
                update(BookingDraftRow)
                .where(
                    BookingDraftRow.tenant_id == tenant_id.value,
                    BookingDraftRow.customer_id == customer_id.value,
                    BookingDraftRow.conversation_id == conversation_id.value,
                    BookingDraftRow.status == "active",
                )
                .values(status="cancelled")
            )
            await session.execute(
                update(SlotHoldRow)
                .where(
                    SlotHoldRow.tenant_id == tenant_id.value,
                    SlotHoldRow.customer_id == customer_id.value,
                    SlotHoldRow.conversation_id == conversation_id.value,
                    SlotHoldRow.status == "active",
                )
                .values(status="released")
            )
            row = BookingDraftRow(
                id=uuid4(),
                tenant_id=tenant_id.value,
                customer_id=customer_id.value,
                conversation_id=conversation_id.value,
                service_id=service_id.value,
                reschedule_booking_id=(
                    reschedule_booking_id.value if reschedule_booking_id else None
                ),
                status="active",
                expires_at=now + context.policy.draft_duration,
            )
            session.add(row)
            conversation = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.tenant_id == tenant_id.value,
                    ConversationRow.id == conversation_id.value,
                    ConversationRow.customer_id == customer_id.value,
                )
            )
            if conversation is None:
                raise BookingNotFoundError()
            conversation.active_workflow = "booking:date"
            await session.flush()
            return _draft(row)

    async def get_active_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        *,
        now: datetime,
    ) -> BookingDraft | None:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(BookingDraftRow)
                .where(
                    BookingDraftRow.tenant_id == tenant_id.value,
                    BookingDraftRow.customer_id == customer_id.value,
                    BookingDraftRow.conversation_id == conversation_id.value,
                    BookingDraftRow.status == "active",
                )
                .order_by(BookingDraftRow.created_at.desc())
                .limit(1)
            )
            if row is None:
                return None
            if row.expires_at <= now:
                row.status = "expired"
                if row.hold_id:
                    await session.execute(
                        update(SlotHoldRow)
                        .where(
                            SlotHoldRow.tenant_id == tenant_id.value,
                            SlotHoldRow.id == row.hold_id,
                            SlotHoldRow.status == "active",
                        )
                        .values(status="expired")
                    )
                return None
            return _draft(row)

    async def _owned_draft(
        self,
        session: AsyncSession,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        now: datetime,
    ) -> BookingDraftRow:
        row = await session.scalar(
            select(BookingDraftRow)
            .where(
                BookingDraftRow.tenant_id == tenant_id.value,
                BookingDraftRow.customer_id == customer_id.value,
                BookingDraftRow.id == draft_id.value,
            )
            .with_for_update()
        )
        if row is None or row.status != "active":
            raise BookingNotFoundError()
        if row.expires_at <= now:
            row.status = "expired"
            raise BookingExpiredError()
        return row

    async def select_date(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        selected_date: date,
        *,
        now: datetime,
    ) -> BookingDraft:
        async with self._session_factory() as session, session.begin():
            row = await self._owned_draft(session, tenant_id, customer_id, draft_id, now)
            context = await self._availability_context(
                session, tenant_id, ServiceId(row.service_id), now=now
            )
            if context is None:
                raise BookingNotFoundError()
            tenant = await session.get(TenantRow, tenant_id.value)
            if tenant is None:
                raise BookingNotFoundError()
            local_today = now.astimezone(__import__("zoneinfo").ZoneInfo(tenant.timezone)).date()
            if (
                selected_date < local_today
                or selected_date
                > (now + context.policy.booking_horizon)
                .astimezone(__import__("zoneinfo").ZoneInfo(tenant.timezone))
                .date()
            ):
                raise BookingPolicyError("The selected date is outside the booking horizon")
            row.selected_date = selected_date
            return _draft(row)

    async def create_hold(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        slot_index: int,
        idempotency_key: str,
        now: datetime,
    ) -> SlotHold:
        if not idempotency_key or len(idempotency_key) > 255 or slot_index < 0:
            raise BookingPolicyError("The hold request is invalid")
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(SlotHoldRow).where(
                    SlotHoldRow.tenant_id == tenant_id.value,
                    SlotHoldRow.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.customer_id != customer_id.value:
                    raise BookingNotFoundError()
                return _hold(existing)
            draft = await self._owned_draft(session, tenant_id, customer_id, draft_id, now)
            if draft.selected_date is None:
                raise BookingPolicyError("Choose a date before choosing a time")
            context = await self._availability_context(
                session, tenant_id, ServiceId(draft.service_id), now=now
            )
            if context is None:
                raise BookingNotFoundError()
            slots = calculate_availability(context, local_date=draft.selected_date, now=now)
            if slot_index >= len(slots):
                raise BookingConflictError()
            selected = slots[slot_index]
            await self._resource_lock(session, tenant_id, selected.resource_id)
            if draft.hold_id is not None:
                await session.execute(
                    update(SlotHoldRow)
                    .where(
                        SlotHoldRow.tenant_id == tenant_id.value,
                        SlotHoldRow.id == draft.hold_id,
                        SlotHoldRow.status == "active",
                    )
                    .values(status="released")
                )
                draft.hold_id = None
                await session.flush()
            refreshed = await self._availability_context(
                session, tenant_id, ServiceId(draft.service_id), now=now
            )
            assert refreshed is not None
            matching = next(
                (
                    item
                    for item in calculate_availability(
                        refreshed, local_date=draft.selected_date, now=now
                    )
                    if item.start_at == selected.start_at
                    and item.resource_id == selected.resource_id
                ),
                None,
            )
            if matching is None:
                raise BookingConflictError()
            hold = SlotHoldRow(
                id=uuid4(),
                tenant_id=tenant_id.value,
                customer_id=customer_id.value,
                conversation_id=draft.conversation_id,
                draft_id=draft.id,
                service_id=draft.service_id,
                resource_id=matching.resource_id.value,
                start_at=matching.start_at,
                end_at=matching.end_at + context.cleanup_buffer,
                expires_at=now + context.policy.hold_duration,
                idempotency_key=idempotency_key,
                status="active",
                timezone=matching.timezone,
            )
            session.add(hold)
            await session.flush()
            draft.hold_id = hold.id
            conversation = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.tenant_id == tenant_id.value,
                    ConversationRow.id == draft.conversation_id,
                )
            )
            if conversation is not None:
                conversation.active_workflow = "booking:name"
            return _hold(hold)

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
    ) -> BookingDraft:
        async with self._session_factory() as session, session.begin():
            draft = await self._owned_draft(session, tenant_id, customer_id, draft_id, now)
            policy_row = await session.get(BookingPolicyRow, tenant_id.value)
            if policy_row is None:
                raise BookingPolicyError("Booking policy is unavailable")
            if name is not None:
                normalized_name = " ".join(name.split())
                if (
                    not normalized_name
                    or len(normalized_name) > policy_row.customer_name_max_length
                ):
                    raise BookingPolicyError("Enter a valid customer name")
                draft.customer_name = normalized_name
            if phone is not None:
                if len(phone) > policy_row.customer_phone_max_length:
                    raise BookingPolicyError("Enter a valid phone number")
                try:
                    parsed = PhoneNumber.parse(phone)
                except ValidationError as exc:
                    raise BookingPolicyError("Enter a valid phone number") from exc
                draft.customer_phone = parsed.normalized_e164 or parsed.raw
            if note is not None:
                normalized_note = note.strip()
                if len(normalized_note) > policy_row.customer_note_max_length:
                    raise BookingPolicyError("The customer note is too long")
                draft.customer_note = normalized_note or None
            conversation = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.tenant_id == tenant_id.value,
                    ConversationRow.id == draft.conversation_id,
                )
            )
            if conversation is not None:
                conversation.active_workflow = (
                    "booking:review"
                    if draft.customer_name and draft.customer_phone
                    else "booking:phone"
                    if draft.customer_name
                    else "booking:name"
                )
            return _draft(draft)

    async def get_hold(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        now: datetime,
    ) -> SlotHold | None:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(SlotHoldRow).where(
                    SlotHoldRow.tenant_id == tenant_id.value,
                    SlotHoldRow.customer_id == customer_id.value,
                    SlotHoldRow.draft_id == draft_id.value,
                    SlotHoldRow.status == "active",
                )
            )
            if row is None:
                return None
            if row.expires_at <= now:
                row.status = "expired"
                return None
            return _hold(row)

    async def cancel_draft(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        conversation_id: ConversationId,
        *,
        now: datetime,
    ) -> bool:
        _ = now
        async with self._session_factory() as session, session.begin():
            await self._identity_lock(session, tenant_id, customer_id)
            drafts = list(
                (
                    await session.scalars(
                        select(BookingDraftRow)
                        .where(
                            BookingDraftRow.tenant_id == tenant_id.value,
                            BookingDraftRow.customer_id == customer_id.value,
                            BookingDraftRow.conversation_id == conversation_id.value,
                            BookingDraftRow.status == "active",
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if not drafts:
                return False
            draft_ids = [row.id for row in drafts]
            await session.execute(
                update(SlotHoldRow)
                .where(
                    SlotHoldRow.tenant_id == tenant_id.value,
                    SlotHoldRow.draft_id.in_(draft_ids),
                    SlotHoldRow.status == "active",
                )
                .values(status="released")
            )
            for row in drafts:
                row.status = "cancelled"
            conversation = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.tenant_id == tenant_id.value,
                    ConversationRow.id == conversation_id.value,
                )
            )
            if conversation is not None:
                conversation.active_workflow = None
            return True

    async def _result(self, session: AsyncSession, row: BookingRow) -> BookingResult:
        service = await session.scalar(
            select(ServiceRow).where(
                ServiceRow.tenant_id == row.tenant_id, ServiceRow.id == row.service_id
            )
        )
        tenant = await session.get(TenantRow, row.tenant_id)
        if service is None or tenant is None or row.public_reference is None:
            raise BookingNotFoundError()
        return BookingResult(
            BookingId(row.id),
            ServiceId(row.service_id),
            row.public_reference,
            str(row.service_snapshot.get("name", service.names.get("en", service.code))),
            row.start_at,
            row.end_at,
            tenant.timezone,
            row.status,
        )

    async def confirm(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        draft_id: BookingDraftId,
        *,
        idempotency_key: str,
        now: datetime,
    ) -> BookingResult:
        if not idempotency_key or len(idempotency_key) > 255:
            raise BookingPolicyError("The confirmation request is invalid")
        try:
            async with self._session_factory() as session, session.begin():
                existing = await session.scalar(
                    select(BookingRow).where(
                        BookingRow.tenant_id == tenant_id.value,
                        BookingRow.idempotency_scope == "confirm",
                        BookingRow.idempotency_value == idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.customer_id != customer_id.value:
                        raise BookingNotFoundError()
                    return await self._result(session, existing)
                confirmed_draft = await session.scalar(
                    select(BookingDraftRow).where(
                        BookingDraftRow.tenant_id == tenant_id.value,
                        BookingDraftRow.customer_id == customer_id.value,
                        BookingDraftRow.id == draft_id.value,
                        BookingDraftRow.status == "confirmed",
                    )
                )
                if confirmed_draft is not None and confirmed_draft.hold_id is not None:
                    confirmed_booking = await session.scalar(
                        select(BookingRow).where(
                            BookingRow.tenant_id == tenant_id.value,
                            BookingRow.customer_id == customer_id.value,
                            BookingRow.hold_id == confirmed_draft.hold_id,
                        )
                    )
                    if confirmed_booking is not None:
                        return await self._result(session, confirmed_booking)
                draft = await self._owned_draft(session, tenant_id, customer_id, draft_id, now)
                if draft.hold_id is None or not draft.customer_name or not draft.customer_phone:
                    raise BookingPolicyError("Complete the booking details before confirmation")
                hold = await session.scalar(
                    select(SlotHoldRow)
                    .where(
                        SlotHoldRow.tenant_id == tenant_id.value,
                        SlotHoldRow.customer_id == customer_id.value,
                        SlotHoldRow.id == draft.hold_id,
                    )
                    .with_for_update()
                )
                if hold is None or hold.status != "active" or hold.expires_at <= now:
                    if hold is not None and hold.status == "active":
                        hold.status = "expired"
                    raise BookingExpiredError()
                resource_id = ResourceId(hold.resource_id)
                await self._resource_lock(session, tenant_id, resource_id)
                service = await session.scalar(
                    select(ServiceRow).where(
                        ServiceRow.tenant_id == tenant_id.value,
                        ServiceRow.id == hold.service_id,
                        ServiceRow.active.is_(True),
                        ServiceRow.bookable.is_(True),
                    )
                )
                if service is None:
                    raise BookingPolicyError("This service is no longer bookable")
                appointment_end = hold.start_at + timedelta(seconds=service.duration_seconds)
                if draft.reschedule_booking_id is not None:
                    booking = await session.scalar(
                        select(BookingRow)
                        .where(
                            BookingRow.tenant_id == tenant_id.value,
                            BookingRow.customer_id == customer_id.value,
                            BookingRow.id == draft.reschedule_booking_id,
                        )
                        .with_for_update()
                    )
                    if booking is None or booking.status != "confirmed":
                        raise BookingNotFoundError()
                    policy_row = await session.get(BookingPolicyRow, tenant_id.value)
                    assert policy_row is not None
                    if booking.start_at - now < timedelta(minutes=policy_row.change_cutoff_minutes):
                        raise BookingPolicyError("This appointment can no longer be rescheduled")
                    sequence = await self._next_history_sequence(session, booking.id)
                    session.add_all(
                        [
                            BookingStatusHistoryRow(
                                id=uuid4(),
                                tenant_id=tenant_id.value,
                                booking_id=booking.id,
                                sequence=sequence,
                                from_status="confirmed",
                                to_status="reschedule_pending",
                                actor="customer",
                                reason="customer_reschedule",
                            ),
                            BookingStatusHistoryRow(
                                id=uuid4(),
                                tenant_id=tenant_id.value,
                                booking_id=booking.id,
                                sequence=sequence + 1,
                                from_status="reschedule_pending",
                                to_status="confirmed",
                                actor="customer",
                                reason="new_hold_confirmed",
                            ),
                        ]
                    )
                    booking.status = "confirmed"
                    booking.resource_id = hold.resource_id
                    booking.start_at = hold.start_at
                    booking.end_at = appointment_end
                    booking.hold_id = hold.id
                    booking.service_snapshot = {
                        "service_id": str(service.id),
                        "name": service.names.get("en", service.code),
                        "duration_seconds": service.duration_seconds,
                        "buffer_seconds": service.buffer_seconds,
                        "price_mode": service.price_mode,
                        "price_min_minor": service.price_min_minor,
                        "price_max_minor": service.price_max_minor,
                        "currency": service.currency,
                    }
                    _booking_event(
                        session,
                        tenant_id,
                        booking,
                        "booking.rescheduled",
                        f"booking:rescheduled:{booking.id}:{sequence}",
                        now,
                    )
                else:
                    booking_id = uuid4()
                    reference = f"NSA-{booking_id.hex[:8].upper()}"
                    booking = BookingRow(
                        id=booking_id,
                        tenant_id=tenant_id.value,
                        customer_id=customer_id.value,
                        conversation_id=draft.conversation_id,
                        service_id=service.id,
                        resource_id=hold.resource_id,
                        hold_id=hold.id,
                        public_reference=reference,
                        start_at=hold.start_at,
                        end_at=appointment_end,
                        status="confirmed",
                        idempotency_scope="confirm",
                        idempotency_value=idempotency_key,
                        service_snapshot={
                            "service_id": str(service.id),
                            "name": service.names.get("en", service.code),
                            "duration_seconds": service.duration_seconds,
                            "buffer_seconds": service.buffer_seconds,
                            "price_mode": service.price_mode,
                            "price_min_minor": service.price_min_minor,
                            "price_max_minor": service.price_max_minor,
                            "currency": service.currency,
                        },
                        customer_snapshot={
                            "name": draft.customer_name,
                            "phone": draft.customer_phone,
                        },
                        notes=draft.customer_note,
                        source="telegram",
                    )
                    session.add(booking)
                    await session.flush()
                    session.add_all(
                        [
                            BookingStatusHistoryRow(
                                id=uuid4(),
                                tenant_id=tenant_id.value,
                                booking_id=booking.id,
                                sequence=1,
                                from_status="draft",
                                to_status="held",
                                actor="customer",
                                reason="slot_hold_created",
                            ),
                            BookingStatusHistoryRow(
                                id=uuid4(),
                                tenant_id=tenant_id.value,
                                booking_id=booking.id,
                                sequence=2,
                                from_status="held",
                                to_status="confirmed",
                                actor="customer",
                                reason="explicit_confirmation",
                            ),
                        ]
                    )
                    _booking_event(
                        session,
                        tenant_id,
                        booking,
                        "booking.confirmed",
                        f"booking:confirmed:{booking.id}",
                        now,
                    )
                hold.status = "consumed"
                draft.status = "confirmed"
                conversation = await session.scalar(
                    select(ConversationRow).where(
                        ConversationRow.tenant_id == tenant_id.value,
                        ConversationRow.id == draft.conversation_id,
                    )
                )
                if conversation is not None:
                    conversation.active_workflow = None
                await session.flush()
                return await self._result(session, booking)
        except IntegrityError as exc:
            raise BookingConflictError() from exc

    async def latest_booking(
        self, tenant_id: TenantId, customer_id: CustomerId, *, now: datetime
    ) -> BookingResult | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(BookingRow)
                .where(
                    BookingRow.tenant_id == tenant_id.value,
                    BookingRow.customer_id == customer_id.value,
                    BookingRow.status == "confirmed",
                    BookingRow.end_at > now,
                )
                .order_by(BookingRow.start_at, BookingRow.id)
                .limit(1)
            )
            return None if row is None else await self._result(session, row)

    async def get_booking(
        self, tenant_id: TenantId, customer_id: CustomerId, booking_id: BookingId
    ) -> BookingResult | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(BookingRow).where(
                    BookingRow.tenant_id == tenant_id.value,
                    BookingRow.customer_id == customer_id.value,
                    BookingRow.id == booking_id.value,
                )
            )
            return None if row is None else await self._result(session, row)

    @staticmethod
    async def _next_history_sequence(session: AsyncSession, booking_id: UUID) -> int:
        latest = await session.scalar(
            select(func.max(BookingStatusHistoryRow.sequence)).where(
                BookingStatusHistoryRow.booking_id == booking_id
            )
        )
        return int(latest or 0) + 1

    async def cancel_booking(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        booking_id: BookingId,
        *,
        now: datetime,
    ) -> BookingResult:
        async with self._session_factory() as session, session.begin():
            booking = await session.scalar(
                select(BookingRow)
                .where(
                    BookingRow.tenant_id == tenant_id.value,
                    BookingRow.customer_id == customer_id.value,
                    BookingRow.id == booking_id.value,
                )
                .with_for_update()
            )
            if booking is None:
                raise BookingNotFoundError()
            if booking.status == "cancelled":
                return await self._result(session, booking)
            if booking.status != "confirmed":
                raise BookingPolicyError("This appointment cannot be cancelled")
            policy = await session.get(BookingPolicyRow, tenant_id.value)
            if policy is None:
                raise BookingPolicyError("Booking policy is unavailable")
            if booking.start_at - now < timedelta(minutes=policy.change_cutoff_minutes):
                raise BookingPolicyError("This appointment can no longer be cancelled")
            booking.status = "cancelled"
            session.add(
                BookingStatusHistoryRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    booking_id=booking.id,
                    sequence=await self._next_history_sequence(session, booking.id),
                    from_status="confirmed",
                    to_status="cancelled",
                    actor="customer",
                    reason="customer_cancelled",
                )
            )
            _booking_event(
                session,
                tenant_id,
                booking,
                "booking.cancelled",
                f"booking:cancelled:{booking.id}",
                now,
            )
            await session.flush()
            return await self._result(session, booking)

    async def expire_holds(self, *, now: datetime, limit: int) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("Expiry limit must be between 1 and 1000")
        async with self._session_factory() as session, session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(SlotHoldRow)
                        .join(TenantRow, TenantRow.id == SlotHoldRow.tenant_id)
                        .join(
                            TenantEntitlementRow,
                            (TenantEntitlementRow.tenant_id == SlotHoldRow.tenant_id)
                            & (TenantEntitlementRow.capability == "booking"),
                        )
                        .where(
                            SlotHoldRow.status == "active",
                            SlotHoldRow.expires_at <= now,
                            TenantRow.status == "active",
                            TenantEntitlementRow.enabled.is_(True),
                        )
                        .order_by(SlotHoldRow.expires_at, SlotHoldRow.id)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for row in rows:
                row.status = "expired"
            return len(rows)

    async def booking_history(
        self, tenant_id: TenantId, customer_id: CustomerId, booking_id: BookingId
    ) -> list[tuple[str, str, datetime]]:
        async with self._session_factory() as session:
            owned = await session.scalar(
                select(BookingRow.id).where(
                    BookingRow.tenant_id == tenant_id.value,
                    BookingRow.customer_id == customer_id.value,
                    BookingRow.id == booking_id.value,
                )
            )
            if owned is None:
                return []
            rows = (
                await session.scalars(
                    select(BookingStatusHistoryRow)
                    .where(
                        BookingStatusHistoryRow.tenant_id == tenant_id.value,
                        BookingStatusHistoryRow.booking_id == booking_id.value,
                    )
                    .order_by(BookingStatusHistoryRow.sequence)
                )
            ).all()
            return [(row.from_status, row.to_status, row.occurred_at) for row in rows]
