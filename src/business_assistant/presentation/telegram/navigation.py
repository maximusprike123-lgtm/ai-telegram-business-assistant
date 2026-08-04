"""Validated Telegram presentation orchestration over Phase 3 application queries."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from business_assistant.application.ai import AdvisoryRoute, AITextRouter
from business_assistant.application.bookings import BookingApplication
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import CategoryNotFoundError
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.handoffs import HandoffApplication, HandoffView
from business_assistant.application.leads import (
    QualificationApplication,
    QualificationSessionStatus,
)
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import (
    BookingDraftId,
    BookingId,
    CategoryId,
    QualificationSessionId,
    ServiceId,
)

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
    qualifications: QualificationApplication | None = None
    handoffs: HandoffApplication | None = None
    ai_router: AITextRouter | None = None


class TelegramNavigation:
    def __init__(self, services: TelegramNavigationServices) -> None:
        self._services = services

    @property
    def _booking_app(self) -> BookingApplication:
        if self._services.bookings is None:
            raise RuntimeError("Booking application is not configured")
        return self._services.bookings

    @property
    def _qualification_app(self) -> QualificationApplication:
        if self._services.qualifications is None:
            raise RuntimeError("Qualification application is not configured")
        return self._services.qualifications

    @property
    def _handoff_app(self) -> HandoffApplication:
        if self._services.handoffs is None:
            raise RuntimeError("Handoff application is not configured")
        return self._services.handoffs

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
        if self._services.qualifications is not None:
            await self._services.qualifications.cancel(identity)
        return self._services.renderer.cancelled()

    async def start_qualification(self, identity: TelegramIdentity) -> RenderedMessage:
        session, schema = await self._qualification_app.start(identity)
        if session.status is QualificationSessionStatus.AWAITING_CONSENT:
            return self._services.renderer.qualification_consent(session, schema)
        if session.status is QualificationSessionStatus.REVIEWING:
            return self._services.renderer.qualification_review(session, schema)
        field = next(
            (item for item in schema.fields if item.key == session.current_field_key), None
        )
        if field is None:
            raise ValueError("Qualification state is invalid")
        return self._services.renderer.qualification_question(field)

    async def qualification_consent(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        *,
        accepted: bool,
        update_key: str,
    ) -> RenderedMessage:
        _, field = await self._qualification_app.consent(identity, session_id, accepted, update_key)
        if not accepted:
            return self._services.renderer.qualification_declined()
        if field is None:
            active = await self._qualification_app.active(identity)
            if active is None:
                raise ValueError("Qualification review is unavailable")
            return self._services.renderer.qualification_review(active[0], active[1])
        return self._services.renderer.qualification_question(field)

    async def qualification_text(
        self, identity: TelegramIdentity, value: str, update_key: str
    ) -> RenderedMessage | None:
        if self._services.qualifications is None:
            return None
        active = await self._qualification_app.active(identity)
        if active is None or active[0].status is not QualificationSessionStatus.IN_PROGRESS:
            return None
        session, next_field = await self._qualification_app.answer(identity, value, update_key)
        if next_field is not None:
            return self._services.renderer.qualification_question(next_field)
        current = await self._qualification_app.active(identity)
        if current is None:
            raise ValueError("Qualification review is unavailable")
        return self._services.renderer.qualification_review(session, current[1])

    async def edit_qualification(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        field_order: int,
    ) -> RenderedMessage:
        active = await self._qualification_app.active(identity)
        if active is None:
            raise ValueError("Qualification is unavailable")
        field = next((item for item in active[1].fields if item.order == field_order), None)
        if field is None:
            raise ValueError("Qualification field is unavailable")
        edited = await self._qualification_app.edit(identity, session_id, field.key)
        return self._services.renderer.qualification_question(edited)

    async def submit_qualification(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        update_key: str,
    ) -> RenderedMessage:
        await self._qualification_app.submit(identity, session_id, update_key)
        handoff = await self.paused(identity)
        return (
            self._services.renderer.handoff(handoff)
            if handoff is not None
            else self._services.renderer.qualification_completed()
        )

    async def human_help(self, identity: TelegramIdentity, *, update_key: str) -> RenderedMessage:
        if self._services.handoffs is None:
            return self._services.renderer.human_placeholder()
        active = await self._handoff_app.active(identity)
        if active is None:
            active = await self._handoff_app.request(
                identity,
                reason_code="explicit_manager_request",
                priority="normal",
                summary="Customer explicitly requested human assistance.",
                idempotency_key=update_key,
            )
        return self._services.renderer.handoff(active)

    async def unsupported(self, identity: TelegramIdentity, *, update_key: str) -> RenderedMessage:
        if self._services.handoffs is None:
            return self._services.renderer.unknown()
        return await self.human_help(identity, update_key=update_key)

    async def route_free_text(
        self, identity: TelegramIdentity, text: str, *, update_key: str
    ) -> RenderedMessage:
        if self._services.ai_router is None:
            return await self.unsupported(identity, update_key=update_key)
        route = await self._services.ai_router.route(
            identity,
            text,
            correlation_id=uuid5(NAMESPACE_URL, f"business-assistant:{update_key}"),
        )
        if route is AdvisoryRoute.HOME:
            return await self.home(identity)
        if route is AdvisoryRoute.CATALOG:
            return await self.catalog(identity)
        if route is AdvisoryRoute.HOURS:
            return await self.hours(identity)
        return await self.unsupported(identity, update_key=update_key)

    async def paused(self, identity: TelegramIdentity) -> HandoffView | None:
        if self._services.handoffs is None:
            return None
        return await self._services.handoffs.active(identity)

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
