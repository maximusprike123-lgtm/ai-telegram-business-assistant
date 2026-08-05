import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.bookings import BookingApplication, calculate_availability
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import (
    BookingConflictError,
    BookingExpiredError,
    BookingPolicyError,
)
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import BookingDraftId, Locale
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBookingStore,
    SQLAlchemyTelegramIdentityStore,
)
from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_RESOURCE_IDS,
    NORTHSTAR_TENANT_ID,
    northstar_services,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    BookingDraftRow,
    BookingRow,
    BookingStatusHistoryRow,
    OutboxEventRow,
    ServiceResourceRow,
    SlotHoldRow,
)
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)
from business_assistant.presentation.telegram import TelegramRenderer
from business_assistant.presentation.telegram.navigation import (
    TelegramNavigation,
    TelegramNavigationServices,
)

pytestmark = pytest.mark.postgresql

NOW = datetime(2026, 8, 3, 3, tzinfo=UTC)


@dataclass(frozen=True)
class FixedClock:
    instant: datetime = NOW

    def now(self) -> datetime:
        return self.instant


async def identity(factory: async_sessionmaker[AsyncSession], external_id: int):
    return await SQLAlchemyTelegramIdentityStore(factory).resolve(
        NORTHSTAR_TENANT_ID,
        external_user_id=str(external_id),
        external_chat_id=str(external_id),
        requested_locale="fr",
        now=NOW,
    )


@pytest.mark.asyncio
async def test_hold_confirm_cancel_and_history_are_durable_and_idempotent(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 5001)
    store = SQLAlchemyBookingStore(factory)
    service = northstar_services()[0]
    selected_date = date(2026, 8, 10)

    context = await store.availability_context(owner.tenant_id, service.id, now=NOW)
    assert context is not None
    slots = calculate_availability(context, local_date=selected_date, now=NOW)
    assert slots and [slot.start_at for slot in slots] == sorted(slot.start_at for slot in slots)

    draft = await store.start_draft(
        owner.tenant_id,
        owner.customer_id,
        owner.conversation_id,
        service.id,
        now=NOW,
    )
    draft = await store.select_date(
        owner.tenant_id, owner.customer_id, draft.id, selected_date, now=NOW
    )
    hold = await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        slot_index=0,
        idempotency_key="hold-owner-1",
        now=NOW,
    )
    duplicate_hold = await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        slot_index=0,
        idempotency_key="hold-owner-1",
        now=NOW,
    )
    assert duplicate_hold.id == hold.id
    await store.update_contact(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        name="Alex Demo",
        phone="+1 555 010 0148",
        note=None,
        now=NOW,
    )
    booking = await store.confirm(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        idempotency_key="confirm-owner-1",
        now=NOW,
    )
    duplicate = await store.confirm(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        idempotency_key="confirm-owner-1",
        now=NOW,
    )
    assert duplicate.id == booking.id
    assert booking.public_reference.startswith("NSA-")
    assert await store.latest_booking(owner.tenant_id, owner.customer_id, now=NOW) == booking
    assert await store.get_booking(owner.tenant_id, owner.customer_id, booking.id) == booking
    history = await store.booking_history(owner.tenant_id, owner.customer_id, booking.id)
    assert [(old, new) for old, new, _ in history] == [
        ("draft", "held"),
        ("held", "confirmed"),
    ]
    with pytest.raises(BookingPolicyError, match="no longer"):
        await store.cancel_booking(
            owner.tenant_id,
            owner.customer_id,
            booking.id,
            now=booking.start_at - timedelta(hours=1),
        )
    assert (await store.get_booking(owner.tenant_id, owner.customer_id, booking.id)).status == (
        "confirmed"
    )
    cancelled = await store.cancel_booking(owner.tenant_id, owner.customer_id, booking.id, now=NOW)
    repeated = await store.cancel_booking(owner.tenant_id, owner.customer_id, booking.id, now=NOW)
    assert cancelled.status == repeated.status == "cancelled"
    assert (await store.booking_history(owner.tenant_id, owner.customer_id, booking.id))[-1][
        :2
    ] == ("confirmed", "cancelled")
    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(OutboxEventRow).order_by(OutboxEventRow.occurred_at, OutboxEventRow.id)
                )
            ).all()
        )
    assert {item.event_type for item in events} == {
        "booking.confirmed",
        "booking.cancelled",
    }
    assert all("phone" not in item.payload and "name" not in item.payload for item in events)


@pytest.mark.asyncio
async def test_expired_hold_and_manual_expiry_do_not_confirm(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 5002)
    store = SQLAlchemyBookingStore(factory)
    service = northstar_services()[0]
    draft = await store.start_draft(
        owner.tenant_id, owner.customer_id, owner.conversation_id, service.id, now=NOW
    )
    await store.select_date(
        owner.tenant_id, owner.customer_id, draft.id, date(2026, 8, 10), now=NOW
    )
    await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        slot_index=0,
        idempotency_key="hold-expiry",
        now=NOW,
    )
    await store.update_contact(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        name="Taylor Demo",
        phone="+1 555 010 0199",
        note=None,
        now=NOW,
    )
    expired_at = NOW + timedelta(minutes=6)
    assert await store.expire_holds(now=expired_at, limit=100) == 1
    with pytest.raises(BookingExpiredError):
        await store.confirm(
            owner.tenant_id,
            owner.customer_id,
            draft.id,
            idempotency_key="confirm-expired",
            now=expired_at,
        )


@pytest.mark.asyncio
async def test_concurrent_last_slot_has_one_winner_and_cross_tenant_ids_do_not_resolve(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    service = northstar_services()[0]
    async with factory() as session, session.begin():
        await session.execute(
            update(ServiceResourceRow)
            .where(
                ServiceResourceRow.tenant_id == NORTHSTAR_TENANT_ID.value,
                ServiceResourceRow.service_id == service.id.value,
                ServiceResourceRow.resource_id == NORTHSTAR_RESOURCE_IDS[1],
            )
            .values(active=False)
        )
    first, second = await asyncio.gather(identity(factory, 5101), identity(factory, 5102))
    store = SQLAlchemyBookingStore(factory)

    async def prepared(user, key: str):
        draft = await store.start_draft(
            user.tenant_id, user.customer_id, user.conversation_id, service.id, now=NOW
        )
        await store.select_date(
            user.tenant_id, user.customer_id, draft.id, date(2026, 8, 10), now=NOW
        )
        return draft, key

    first_draft, second_draft = await asyncio.gather(
        prepared(first, "race-first"), prepared(second, "race-second")
    )

    async def contend(user, prepared_value):
        draft, key = prepared_value
        try:
            return await store.create_hold(
                user.tenant_id,
                user.customer_id,
                draft.id,
                slot_index=0,
                idempotency_key=key,
                now=NOW,
            )
        except BookingConflictError:
            return None

    outcomes = await asyncio.gather(contend(first, first_draft), contend(second, second_draft))
    assert sum(item is not None for item in outcomes) == 1
    winner = first if outcomes[0] is not None else second
    loser = second if winner is first else first
    winner_draft = first_draft[0] if winner is first else second_draft[0]
    assert (
        await store.get_active_draft(
            winner.tenant_id, loser.customer_id, winner_draft.conversation_id, now=NOW
        )
        is None
    )


@pytest.mark.asyncio
async def test_reschedule_is_atomic_and_preserves_one_booking_record(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 5201)
    store = SQLAlchemyBookingStore(factory)
    service = northstar_services()[1]
    draft = await store.start_draft(
        owner.tenant_id, owner.customer_id, owner.conversation_id, service.id, now=NOW
    )
    await store.select_date(
        owner.tenant_id, owner.customer_id, draft.id, date(2026, 8, 10), now=NOW
    )
    await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        slot_index=0,
        idempotency_key="reschedule-original-hold",
        now=NOW,
    )
    await store.update_contact(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        name="Morgan Demo",
        phone="+1 555 010 0177",
        note="Fictional note",
        now=NOW,
    )
    original = await store.confirm(
        owner.tenant_id,
        owner.customer_id,
        draft.id,
        idempotency_key="reschedule-original-confirm",
        now=NOW,
    )
    failed = await store.start_draft(
        owner.tenant_id,
        owner.customer_id,
        owner.conversation_id,
        service.id,
        now=NOW,
        reschedule_booking_id=original.id,
    )
    await store.select_date(
        owner.tenant_id, owner.customer_id, failed.id, date(2026, 8, 11), now=NOW
    )
    await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        failed.id,
        slot_index=0,
        idempotency_key="reschedule-failed-hold",
        now=NOW,
    )
    await store.update_contact(
        owner.tenant_id,
        owner.customer_id,
        failed.id,
        name="Morgan Demo",
        phone="+1 555 010 0177",
        note=None,
        now=NOW,
    )
    with pytest.raises(BookingExpiredError):
        await store.confirm(
            owner.tenant_id,
            owner.customer_id,
            failed.id,
            idempotency_key="reschedule-failed-confirm",
            now=NOW + timedelta(minutes=6),
        )
    unchanged = await store.get_booking(owner.tenant_id, owner.customer_id, original.id)
    assert unchanged is not None and unchanged.start_at == original.start_at
    replacement = await store.start_draft(
        owner.tenant_id,
        owner.customer_id,
        owner.conversation_id,
        service.id,
        now=NOW,
        reschedule_booking_id=original.id,
    )
    await store.select_date(
        owner.tenant_id, owner.customer_id, replacement.id, date(2026, 8, 11), now=NOW
    )
    await store.create_hold(
        owner.tenant_id,
        owner.customer_id,
        replacement.id,
        slot_index=0,
        idempotency_key="reschedule-new-hold",
        now=NOW,
    )
    await store.update_contact(
        owner.tenant_id,
        owner.customer_id,
        replacement.id,
        name="Morgan Demo",
        phone="+1 555 010 0177",
        note=None,
        now=NOW,
    )
    changed = await store.confirm(
        owner.tenant_id,
        owner.customer_id,
        replacement.id,
        idempotency_key="reschedule-new-confirm",
        now=NOW,
    )
    assert changed.id == original.id
    assert changed.start_at != original.start_at
    async with factory() as session:
        booking_count = await session.scalar(
            select(BookingRow).where(BookingRow.id == original.id.value)
        )
        histories = list(
            (
                await session.scalars(
                    select(BookingStatusHistoryRow).where(
                        BookingStatusHistoryRow.booking_id == original.id.value
                    )
                )
            ).all()
        )
        active_holds = list(
            (await session.scalars(select(SlotHoldRow).where(SlotHoldRow.status == "active"))).all()
        )
        confirmed_drafts = list(
            (
                await session.scalars(
                    select(BookingDraftRow).where(BookingDraftRow.status == "confirmed")
                )
            ).all()
        )
    assert booking_count is not None
    assert [(item.from_status, item.to_status) for item in histories][-2:] == [
        ("confirmed", "reschedule_pending"),
        ("reschedule_pending", "confirmed"),
    ]
    assert active_holds == []
    assert len(confirmed_drafts) == 2
    assert owner.locale is Locale.EN


@pytest.mark.asyncio
async def test_telegram_navigation_completes_persisted_english_booking_flow(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 5301)
    clock = FixedClock()
    renderer = TelegramRenderer()

    def uow_factory() -> Phase3UnitOfWork:
        return cast(Phase3UnitOfWork, SQLAlchemyUnitOfWork(factory))

    typed_factory: Phase3UnitOfWorkFactory = uow_factory
    navigation = TelegramNavigation(
        TelegramNavigationServices(
            GetTenantPublicProfile(typed_factory, clock),
            ListServiceCategories(typed_factory),
            ListServices(typed_factory),
            GetService(typed_factory),
            GetBusinessHours(typed_factory),
            GetBusinessStatus(typed_factory, clock),
            GetNextOpening(typed_factory, clock),
            renderer,
            BookingApplication(SQLAlchemyBookingStore(factory), clock),
        )
    )
    services_page = await navigation.booking_services(owner)
    assert "Book an appointment" in services_page.text
    service_button = services_page.button_rows[0][0]
    assert service_button.entity_id is not None
    dates_page = await navigation.start_booking(owner, northstar_services()[0].id)
    date_button = dates_page.button_rows[0][0]
    assert date_button.entity_id is not None and date_button.page is not None
    times_page = await navigation.choose_booking_date(
        owner,
        BookingDraftId.parse(date_button.entity_id),
        date_button.page,
    )
    time_button = times_page.button_rows[0][0]
    assert time_button.entity_id is not None and time_button.page is not None
    draft_id = BookingDraftId.parse(time_button.entity_id)
    name_page = await navigation.choose_booking_slot(owner, draft_id, time_button.page)
    assert "held for 5 minutes" in name_page.text
    assert "phone" in (await navigation.booking_text(owner, "Jamie Demo")).text
    review = await navigation.booking_text(owner, "+1 555 010 0188")
    assert review is not None and "Review the appointment" in review.text
    confirmed = await navigation.confirm_booking(owner, draft_id)
    assert "Appointment confirmed" in confirmed.text
    assert "notified" not in confirmed.text.lower()
    appointment = await navigation.my_booking(owner)
    assert "My appointment" in appointment.text
    assert all(not ("\u0400" <= character <= "\u04ff") for character in confirmed.text)
