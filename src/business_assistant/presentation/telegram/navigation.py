"""Validated Telegram presentation orchestration over Phase 3 application queries."""

from dataclasses import dataclass

from business_assistant.application.bookings import BookingApplication
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import CategoryNotFoundError
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import BookingDraftId, BookingId, CategoryId, ServiceId

from .callbacks import booking_date_from_page, booking_slot_page
from .models import RenderedMessage
from .renderer import TelegramRenderer


@dataclass(frozen=True, slots=True)
class TelegramNavigationServices:
    profile: GetTenantPublicProfile
    categories: ListServiceCategories
    services: ListServices
    service: GetService
    hours: GetBusinessHours
    status: GetBusinessStatus
    next_opening: GetNextOpening
    renderer: TelegramRenderer
    bookings: BookingApplication | None = None


class TelegramNavigation:
    def __init__(self, services: TelegramNavigationServices) -> None:
        self._services = services

    @property
    def _booking_app(self) -> BookingApplication:
        if self._services.bookings is None:
            raise RuntimeError("Booking application is not configured")
        return self._services.bookings

    @staticmethod
    def _principal(identity: TelegramIdentity) -> Principal:
        return Principal(
            f"telegram-conversation:{identity.conversation_id}", identity.tenant_id, Role.VIEWER
        )

    async def home(self, identity: TelegramIdentity) -> RenderedMessage:
        profile = await self._services.profile.execute(self._principal(identity), identity.locale)
        return self._services.renderer.home(profile)

    async def catalog(self, identity: TelegramIdentity, page: int = 0) -> RenderedMessage:
        categories = await self._services.categories.execute(
            self._principal(identity), identity.locale
        )
        return self._services.renderer.catalog(categories, page)

    async def category(
        self, identity: TelegramIdentity, category_id: CategoryId, page: int = 0
    ) -> RenderedMessage:
        principal = self._principal(identity)
        categories = await self._services.categories.execute(principal, identity.locale)
        category = next((item for item in categories if item.id == str(category_id)), None)
        if category is None:
            raise CategoryNotFoundError()
        services = await self._services.services.execute(principal, identity.locale, category_id)
        return self._services.renderer.services(category, services, page)

    async def service(self, identity: TelegramIdentity, service_id: ServiceId) -> RenderedMessage:
        service = await self._services.service.execute(
            self._principal(identity), service_id, identity.locale
        )
        return self._services.renderer.service(service)

    async def hours(self, identity: TelegramIdentity) -> RenderedMessage:
        principal = self._principal(identity)
        status = await self._services.status.execute(principal)
        days = await self._services.hours.execute(
            principal, status.local_date, days=7, locale=identity.locale
        )
        next_opening = await self._services.next_opening.execute(principal)
        return self._services.renderer.hours(days, status, next_opening)

    async def booking_services(self, identity: TelegramIdentity) -> RenderedMessage:
        services = await self._services.services.execute(
            self._principal(identity), identity.locale, None
        )
        return self._services.renderer.booking_services(services)

    async def start_booking(
        self, identity: TelegramIdentity, service_id: ServiceId
    ) -> RenderedMessage:
        draft = await self._booking_app.start(identity, service_id)
        service = await self._services.service.execute(
            self._principal(identity), service_id, identity.locale
        )
        dates = await self._booking_app.dates(identity, draft)
        return self._services.renderer.booking_dates(service, draft, dates)

    async def choose_booking_date(
        self, identity: TelegramIdentity, draft_id: BookingDraftId, offset: int
    ) -> RenderedMessage:
        active = await self._booking_app.active(identity)
        if active is None or active.id != draft_id:
            return self._services.renderer.booking_expired()
        dates = await self._booking_app.dates(identity, active)
        selected_date = booking_date_from_page(offset)
        if selected_date not in dates:
            return self._services.renderer.booking_expired()
        draft, slots = await self._booking_app.choose_date(identity, draft_id, selected_date)
        service = await self._services.service.execute(
            self._principal(identity), draft.service_id, identity.locale
        )
        return self._services.renderer.booking_times(service, draft, slots)

    async def choose_booking_slot(
        self, identity: TelegramIdentity, draft_id: BookingDraftId, slot_choice: int
    ) -> RenderedMessage:
        draft = await self._booking_app.active(identity)
        if draft is None or draft.id != draft_id or draft.selected_date is None:
            return self._services.renderer.booking_expired()
        draft, slots = await self._booking_app.choose_date(identity, draft_id, draft.selected_date)
        slot_index = next(
            (
                index
                for index, slot in enumerate(slots)
                if booking_slot_page(slot.start_at, slot.timezone) == slot_choice
            ),
            -1,
        )
        if slot_index < 0:
            return self._services.renderer.booking_expired()
        hold = await self._booking_app.hold(
            identity,
            draft_id,
            slot_index,
            f"telegram-hold:{draft_id}:{slot_choice}",
        )
        return self._services.renderer.ask_name(hold)

    async def booking_text(self, identity: TelegramIdentity, value: str) -> RenderedMessage | None:
        draft = await self._booking_app.active(identity)
        if draft is None or draft.hold_id is None:
            return None
        if draft.customer_name is None:
            await self._booking_app.contact(identity, draft.id, name=value)
            return self._services.renderer.ask_phone()
        if draft.customer_phone is None:
            draft = await self._booking_app.contact(identity, draft.id, phone=value)
            hold = await self._booking_app.current_hold(identity, draft.id)
            if hold is None:
                return self._services.renderer.booking_expired()
            service = await self._services.service.execute(
                self._principal(identity), draft.service_id, identity.locale
            )
            return self._services.renderer.booking_review(service, draft, hold)
        return None

    async def confirm_booking(
        self, identity: TelegramIdentity, draft_id: BookingDraftId
    ) -> RenderedMessage:
        result = await self._booking_app.confirm(identity, draft_id, f"telegram-confirm:{draft_id}")
        return self._services.renderer.booking_confirmed(result)

    async def cancel_flow(self, identity: TelegramIdentity) -> RenderedMessage:
        await self._booking_app.abandon(identity)
        return self._services.renderer.cancelled()

    async def my_booking(self, identity: TelegramIdentity) -> RenderedMessage:
        booking = await self._booking_app.latest(identity)
        return (
            self._services.renderer.no_booking()
            if booking is None
            else self._services.renderer.my_booking(booking)
        )

    async def ask_cancel_booking(
        self, identity: TelegramIdentity, booking_id: BookingId
    ) -> RenderedMessage:
        booking = await self._booking_app.get(identity, booking_id)
        if booking is None:
            return self._services.renderer.no_booking()
        return self._services.renderer.appointment_cancel_confirmation(booking)

    async def cancel_booking(
        self, identity: TelegramIdentity, booking_id: BookingId
    ) -> RenderedMessage:
        booking = await self._booking_app.cancel(identity, booking_id)
        return self._services.renderer.appointment_cancelled(booking)

    async def start_reschedule(
        self, identity: TelegramIdentity, booking_id: BookingId
    ) -> RenderedMessage:
        draft = await self._booking_app.start_reschedule(identity, booking_id)
        service = await self._services.service.execute(
            self._principal(identity), draft.service_id, identity.locale
        )
        dates = await self._booking_app.dates(identity, draft)
        return self._services.renderer.booking_dates(service, draft, dates)
