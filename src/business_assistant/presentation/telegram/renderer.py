"""English-only, HTML-safe Telegram rendering with explicit platform limits."""

from datetime import date
from html import escape
from zoneinfo import ZoneInfo

from business_assistant.application.bookings import (
    AvailableSlot,
    BookingDraft,
    BookingResult,
    SlotHold,
)
from business_assistant.application.catalog import ServiceCategoryDTO, ServiceDTO
from business_assistant.application.handoffs import HandoffView
from business_assistant.application.knowledge import KnowledgeAnswer
from business_assistant.application.leads import (
    QualificationField,
    QualificationSchema,
    QualificationSession,
    Sensitivity,
)
from business_assistant.application.scheduling import (
    BusinessDayDTO,
    BusinessStatusDTO,
    NextOpeningDTO,
)
from business_assistant.application.tenants import TenantPublicProfileDTO

from .callbacks import CallbackAction, booking_date_page, booking_slot_page
from .models import NavigationButton, RenderedMessage

TELEGRAM_TEXT_LIMIT = 4096
SAFE_TEXT_LIMIT = 4000
MAX_BUTTONS_PER_ROW = 2
MAX_BUTTON_ROWS = 8
PAGE_SIZE = 6


def _safe(value: str) -> str:
    return escape(value, quote=False)


def _button(
    label: str,
    action: CallbackAction,
    entity_id: str | None = None,
    page: int | None = None,
) -> NavigationButton:
    return NavigationButton(label[:64], action, entity_id, page)


class TelegramRenderer:
    def __init__(self, *, ai_enabled: bool = False) -> None:
        self._ai_enabled = ai_enabled

    def home(self, profile: TenantPublicProfileDTO) -> RenderedMessage:
        status = "Open now" if profile.status.open_now else "Closed now"
        contact = []
        if profile.address:
            contact.append(f"<b>Location:</b> {_safe(profile.address)}")
        if profile.public_phone:
            contact.append(f"<b>Phone:</b> {_safe(profile.public_phone)}")
        if profile.public_email:
            contact.append(f"<b>Email:</b> {_safe(profile.public_email)}")
        contact_block = "\n" + "\n".join(contact) + "\n" if contact else "\n"
        ai_notice = (
            "Free text may be classified by a configured AI provider, but validated application "
            "rules remain authoritative."
            if self._ai_enabled
            else "AI is not enabled."
        )
        text = (
            f"<b>{_safe(profile.name)}</b>\n"
            f"{_safe(profile.description)}\n\n"
            f"<b>{status}</b> · {_safe(profile.status.local_time)} "
            f"({_safe(profile.timezone)})\n"
            f"{contact_block}\n"
            "This is a fictional portfolio demo. It can show verified business information, "
            f"and create fictional demo appointments. {ai_notice} It stores numeric Telegram "
            "identifiers for continuity and duplicate protection; use Privacy for details."
        )
        return RenderedMessage(
            text,
            (
                (
                    _button("Services", CallbackAction.CATALOG),
                    _button("Business hours", CallbackAction.HOURS),
                ),
                (
                    _button("Book appointment", CallbackAction.BOOK),
                    _button("My appointment", CallbackAction.MY_BOOKING),
                ),
                (_button("Request service", CallbackAction.QUALIFY),),
                (
                    _button("Privacy", CallbackAction.PRIVACY),
                    _button("Human help", CallbackAction.HUMAN),
                ),
            ),
            show_reply_menu=True,
        )

    def catalog(self, categories: tuple[ServiceCategoryDTO, ...], page: int = 0) -> RenderedMessage:
        start = page * PAGE_SIZE
        rows = tuple(
            (_button(category.name, CallbackAction.CATEGORY, category.id),)
            for category in categories[start : start + PAGE_SIZE]
        )
        paging = []
        if page > 0:
            paging.append(_button("Previous", CallbackAction.CATALOG, page=page - 1))
        if start + PAGE_SIZE < len(categories):
            paging.append(_button("Next", CallbackAction.CATALOG, page=page + 1))
        paging_row = (tuple(paging),) if paging else ()
        return RenderedMessage(
            "<b>Services</b>\nChoose a category to see active services.",
            (*rows, *paging_row, (_button("Home", CallbackAction.HOME),)),
        )

    def services(
        self, category: ServiceCategoryDTO, services: tuple[ServiceDTO, ...], page: int = 0
    ) -> RenderedMessage:
        start = page * PAGE_SIZE
        rows = tuple(
            (_button(service.name, CallbackAction.SERVICE, service.id),)
            for service in services[start : start + PAGE_SIZE]
        )
        paging = []
        if page > 0:
            paging.append(_button("Previous", CallbackAction.CATEGORY, category.id, page - 1))
        if start + PAGE_SIZE < len(services):
            paging.append(_button("Next", CallbackAction.CATEGORY, category.id, page + 1))
        paging_row = (tuple(paging),) if paging else ()
        return RenderedMessage(
            f"<b>{_safe(category.name)}</b>\nChoose a service for verified details.",
            (*rows, *paging_row, (_button("Back to services", CallbackAction.CATALOG),)),
        )

    def service(self, service: ServiceDTO) -> RenderedMessage:
        price = service.price.display or "Price is not displayed"
        notes = ""
        if service.preparation_notes:
            notes += f"\n\n<b>Before your visit:</b> {_safe(service.preparation_notes)}"
        if service.eligibility_notes:
            notes += f"\n\n<b>Please note:</b> {_safe(service.eligibility_notes)}"
        bookable = (
            "Choose Book now to continue."
            if service.bookable
            else ("This service is not available for booking.")
        )
        text = (
            f"<b>{_safe(service.name)}</b>\n"
            f"{_safe(service.description)}\n\n"
            f"<b>Duration:</b> {_safe(service.duration_display)}\n"
            f"<b>Price:</b> {_safe(price)}"
            f"{notes}\n\n{bookable}"
        )
        return RenderedMessage(
            text,
            (
                *(
                    (_button("Book now", CallbackAction.BOOK_SERVICE, service.id),)
                    if service.bookable
                    else ()
                ),
                (_button("Back to services", CallbackAction.CATALOG),),
                (_button("Home", CallbackAction.HOME),),
            ),
        )

    def hours(
        self,
        days: tuple[BusinessDayDTO, ...],
        status: BusinessStatusDTO,
        next_opening: NextOpeningDTO,
    ) -> RenderedMessage:
        lines = ["<b>Business hours</b>"]
        for day in days:
            intervals = (
                "Closed"
                if day.closed
                else ", ".join(
                    f"{_safe(interval.start_local)}-{_safe(interval.end_local)}"
                    for interval in day.intervals
                )
            )
            lines.append(f"{_safe(day.day_label)}: {intervals}")
        current = "Open now" if status.open_now else "Closed now"
        lines.extend(["", f"<b>{current}</b> at {_safe(status.local_time)}."])
        if not status.open_now and next_opening.next_opening_local:
            lines.append(f"Next opening: {_safe(next_opening.next_opening_local)}.")
        lines.append(f"Timezone: {_safe(status.timezone)}.")
        return RenderedMessage(
            "\n".join(lines),
            ((_button("Home", CallbackAction.HOME),),),
        )

    def help(self) -> RenderedMessage:
        free_text = (
            "Free-form text uses advisory AI classification and approved knowledge retrieval "
            "with deterministic validation and fallback."
            if self._ai_enabled
            else (
                "Free-form questions receive a safe, deterministic reply because AI is not enabled."
            )
        )
        return RenderedMessage(
            "<b>Help</b>\nUse the menu to browse services, book or manage a fictional demo "
            "appointment, and see opening times. /cancel clears only the active booking flow. "
            f"{free_text}",
            ((_button("Home", CallbackAction.HOME),),),
            show_reply_menu=True,
        )

    def knowledge_answer(self, answer: KnowledgeAnswer) -> RenderedMessage:
        if not answer.answered or not answer.evidence:
            return self.unknown()
        labels: list[str] = []
        for item in answer.evidence:
            label = item.chunk.title
            if item.chunk.section and item.chunk.section != item.chunk.title:
                label = f"{label} — {item.chunk.section}"
            if label not in labels:
                labels.append(label)
        sources = ", ".join(_safe(label) for label in labels)
        return RenderedMessage(
            f"{_safe(answer.text)}\n\n<b>Approved sources:</b> {sources}",
            (
                (_button("Ask a person", CallbackAction.HUMAN),),
                (_button("Home", CallbackAction.HOME),),
            ),
        )

    def privacy(self) -> RenderedMessage:
        ai_processing = (
            " When AI is enabled, free-form text is sent to the configured provider for bounded "
            "classification and, when knowledge is enabled, embedding. The application stores "
            "AI-operation metadata such as model, latency, tokens, and outcome—not customer "
            "prompts, message text, or provider response bodies."
            if self._ai_enabled
            else ""
        )
        return RenderedMessage(
            "<b>Privacy notice · demo-v1</b>\nThis fictional demo stores Telegram numeric user "
            "and chat identifiers to keep a tenant-scoped conversation and prevent duplicate "
            "updates. It does not store message bodies, usernames, profile names, or raw updates. "
            f"Do not send sensitive or real customer information.{ai_processing}",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def human_placeholder(self) -> RenderedMessage:
        return RenderedMessage(
            "Human handoff is not enabled in this demo phase. No request has been created. "
            "Use the verified contact details on the home screen if you need assistance.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def qualification_consent(
        self, session: QualificationSession, schema: QualificationSchema
    ) -> RenderedMessage:
        return RenderedMessage(
            f"<b>{_safe(schema.title)}</b>\n"
            f"Before collecting request details, please review the purpose: "
            f"{_safe(schema.consent_purpose)}\n\n"
            f"Consent version: <code>{_safe(schema.consent_version)}</code>. "
            "Accept to continue, or decline to finish without creating a lead.",
            (
                (
                    _button(
                        "Accept and continue",
                        CallbackAction.QUALIFY_CONSENT_ACCEPT,
                        str(session.id),
                    ),
                ),
                (
                    _button(
                        "Decline",
                        CallbackAction.QUALIFY_CONSENT_DECLINE,
                        str(session.id),
                    ),
                ),
            ),
        )

    def qualification_declined(self) -> RenderedMessage:
        return RenderedMessage(
            "Consent was declined. No lead was created and qualification has ended.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def qualification_question(self, field: QualificationField) -> RenderedMessage:
        choices = (
            f"\nAllowed values: {_safe(', '.join(field.validation.options))}."
            if field.validation.options
            else ""
        )
        return RenderedMessage(
            f"<b>{_safe(field.label)}</b>\n{_safe(field.prompt)}{choices}",
            ((_button("Cancel request", CallbackAction.FLOW_CANCEL),),),
        )

    def qualification_correction(self, correction: str) -> RenderedMessage:
        return RenderedMessage(
            f"{_safe(correction)} Please try again.",
            ((_button("Cancel request", CallbackAction.FLOW_CANCEL),),),
        )

    def qualification_review(
        self, session: QualificationSession, schema: QualificationSchema
    ) -> RenderedMessage:
        lines = ["<b>Review your service request</b>"]
        rows = []
        for field in schema.fields:
            value = session.answers.get(field.key)
            shown = (
                "Not provided"
                if value is None
                else ", ".join(value)
                if isinstance(value, tuple)
                else str(value)
            )
            if field.sensitivity is Sensitivity.SENSITIVE and field.field_type.value == "phone":
                shown = f"ending {shown[-4:]}" if len(shown) >= 4 else "provided"
            lines.append(f"<b>{_safe(field.label)}:</b> {_safe(shown)}")
            rows.append(
                (
                    _button(
                        f"Edit {field.label}",
                        CallbackAction.QUALIFY_EDIT,
                        str(session.id),
                        field.order,
                    ),
                )
            )
        lines.append("\nSubmit only if every detail is correct.")
        return RenderedMessage(
            "\n".join(lines),
            (
                *rows[:6],
                (_button("Submit request", CallbackAction.QUALIFY_SUBMIT, str(session.id)),),
                (_button("Cancel request", CallbackAction.FLOW_CANCEL),),
            ),
        )

    def qualification_completed(self) -> RenderedMessage:
        return RenderedMessage(
            "<b>Service request submitted</b>\nThe fictional Northstar team can now review "
            "the validated details. This did not diagnose the vehicle or create an appointment.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def handoff(self, handoff: HandoffView) -> RenderedMessage:
        timezone = str(handoff.context.get("timezone", "UTC"))
        local_due = handoff.response_due_at.astimezone(ZoneInfo(timezone))
        state = (
            "A team member is handling this request."
            if handoff.status == "claimed"
            else "The request is queued for a team member."
        )
        return RenderedMessage(
            f"<b>Human help · {_safe(handoff.status)}</b>\n{_safe(state)} "
            f"Expected response by {local_due.strftime('%A, %d %B %Y at %H:%M')} "
            f"({_safe(timezone)}). Bot replies are paused until staff returns control.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def cancelled(self) -> RenderedMessage:
        return RenderedMessage(
            "There is no active workflow or appointment hold to cancel. Navigation was reset.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def booking_services(self, services: tuple[ServiceDTO, ...]) -> RenderedMessage:
        rows = tuple(
            (_button(item.name, CallbackAction.BOOK_SERVICE, item.id),)
            for item in services[:PAGE_SIZE]
            if item.bookable
        )
        return RenderedMessage(
            "<b>Book an appointment</b>\nChoose an active service.",
            (*rows, (_button("Home", CallbackAction.HOME),)),
        )

    def booking_dates(
        self, service: ServiceDTO, draft: BookingDraft, dates: tuple[date, ...]
    ) -> RenderedMessage:
        rows = tuple(
            (
                _button(
                    item.strftime("%a, %d %b"),
                    CallbackAction.BOOK_DATE,
                    str(draft.id),
                    booking_date_page(item),
                ),
            )
            for item in dates
        )
        if not rows:
            return self.no_slots()
        return RenderedMessage(
            f"<b>{_safe(service.name)}</b>\nChoose an available date.",
            (*rows, (_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),)),
        )

    def booking_times(
        self, service: ServiceDTO, draft: BookingDraft, slots: tuple[AvailableSlot, ...]
    ) -> RenderedMessage:
        rows = tuple(
            (
                _button(
                    slot.local_time,
                    CallbackAction.BOOK_SLOT,
                    str(draft.id),
                    booking_slot_page(slot.start_at, slot.timezone),
                ),
            )
            for slot in slots[:12]
        )
        if not rows:
            return self.no_slots()
        assert draft.selected_date is not None
        return RenderedMessage(
            f"<b>{_safe(service.name)}</b>\n"
            f"Available times for {draft.selected_date.strftime('%A, %d %B %Y')}. "
            f"Times use {_safe(slots[0].timezone)}.",
            (*rows, (_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),)),
        )

    def ask_name(self, hold: SlotHold) -> RenderedMessage:
        return RenderedMessage(
            "The time is held for 5 minutes. Enter the customer name for this appointment. "
            "Only the validated name is stored; the message body is not retained.",
            ((_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),),),
        )

    def ask_phone(self) -> RenderedMessage:
        return RenderedMessage(
            "Enter the phone number the workshop may use for this appointment. "
            "By continuing, you consent to storing it with this fictional demo booking.",
            ((_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),),),
        )

    def booking_review(
        self, service: ServiceDTO, draft: BookingDraft, hold: SlotHold
    ) -> RenderedMessage:
        local = hold.time_range.start.astimezone(ZoneInfo(hold.timezone))
        phone = draft.customer_phone or ""
        masked_phone = f"ending {phone[-4:]}" if len(phone) >= 4 else "provided"
        return RenderedMessage(
            "<b>Review the appointment</b>\n"
            f"Service: {_safe(service.name)}\n"
            f"When: {local.strftime('%A, %d %B %Y at %H:%M')} "
            f"({_safe(str(local.tzinfo))})\n"
            f"Customer: {_safe(draft.customer_name or '')}\n"
            f"Phone: {_safe(masked_phone)}\n\n"
            "Confirm only if these details are correct. No appointment exists until "
            "confirmation succeeds.",
            (
                (_button("Confirm appointment", CallbackAction.BOOK_CONFIRM, str(draft.id)),),
                (_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),),
            ),
        )

    def booking_confirmed(self, booking: BookingResult) -> RenderedMessage:
        local = booking.start_at.astimezone(ZoneInfo(booking.timezone))
        return RenderedMessage(
            "<b>Appointment confirmed</b>\n"
            f"Reference: <code>{_safe(booking.public_reference)}</code>\n"
            f"Service: {_safe(booking.service_name)}\n"
            f"When: {local.strftime('%A, %d %B %Y at %H:%M')} "
            f"({_safe(booking.timezone)})\n\n"
            "This is a fictional portfolio demo; no real workshop appointment was created.",
            ((_button("My appointment", CallbackAction.MY_BOOKING),),),
        )

    def my_booking(self, booking: BookingResult) -> RenderedMessage:
        local = booking.start_at.astimezone(ZoneInfo(booking.timezone))
        return RenderedMessage(
            "<b>My appointment</b>\n"
            f"Reference: <code>{_safe(booking.public_reference)}</code>\n"
            f"Service: {_safe(booking.service_name)}\n"
            f"When: {local.strftime('%A, %d %B %Y at %H:%M')} ({_safe(booking.timezone)})\n"
            f"Status: {_safe(booking.status)}",
            (
                (_button("Reschedule", CallbackAction.RESCHEDULE, str(booking.id)),),
                (
                    _button(
                        "Cancel appointment", CallbackAction.APPOINTMENT_CANCEL, str(booking.id)
                    ),
                ),
                (_button("Home", CallbackAction.HOME),),
            ),
        )

    def no_booking(self) -> RenderedMessage:
        return RenderedMessage(
            "No eligible upcoming appointment was found for this Telegram identity.",
            ((_button("Book appointment", CallbackAction.BOOK),),),
        )

    def appointment_cancel_confirmation(self, booking: BookingResult) -> RenderedMessage:
        return RenderedMessage(
            f"Cancel appointment <code>{_safe(booking.public_reference)}</code>? "
            "This action is separate from clearing the current menu flow.",
            (
                (
                    _button(
                        "Yes, cancel appointment",
                        CallbackAction.APPOINTMENT_CANCEL_CONFIRM,
                        str(booking.id),
                    ),
                ),
                (_button("Keep appointment", CallbackAction.MY_BOOKING),),
            ),
        )

    def appointment_cancelled(self, booking: BookingResult) -> RenderedMessage:
        return RenderedMessage(
            f"Appointment <code>{_safe(booking.public_reference)}</code> is cancelled.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def no_slots(self) -> RenderedMessage:
        return RenderedMessage(
            "No appointment times are currently available for that selection. "
            "Refresh the booking flow to try another date.",
            (
                (_button("Book appointment", CallbackAction.BOOK),),
                (_button("Home", CallbackAction.HOME),),
            ),
        )

    def booking_expired(self) -> RenderedMessage:
        return RenderedMessage(
            "That held time expired or changed before confirmation. No appointment was created. "
            "Choose a fresh time to continue.",
            ((_button("Book appointment", CallbackAction.BOOK),),),
        )

    def booking_input_invalid(self) -> RenderedMessage:
        return RenderedMessage(
            "That value is not valid for the current booking step. Check the requested format "
            "and try again, or cancel the booking flow.",
            ((_button("Cancel booking flow", CallbackAction.FLOW_CANCEL),),),
        )

    def unknown(self) -> RenderedMessage:
        ending = (
            "The request could not be safely routed, so no AI-proposed action was executed."
            if self._ai_enabled
            else "AI and free-form business answers are not enabled."
        )
        return RenderedMessage(
            "Use the menu to browse verified services, book or manage a fictional demo "
            f"appointment, view business hours, or get help. {ending}",
            ((_button("Home", CallbackAction.HOME),),),
            show_reply_menu=True,
        )

    def callback_recovery(self) -> RenderedMessage:
        return RenderedMessage(
            "That menu action is no longer valid. Please refresh the menu.",
            ((_button("Refresh", CallbackAction.HOME),),),
        )

    def error(self) -> RenderedMessage:
        return RenderedMessage(
            "The request could not be completed safely. Please try again from the home menu.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def split_plain_text(self, value: str) -> tuple[RenderedMessage, ...]:
        if not value:
            return (RenderedMessage(" "),)
        chunks: list[RenderedMessage] = []
        remaining = value
        while remaining:
            cut = min(len(remaining), SAFE_TEXT_LIMIT)
            if cut < len(remaining):
                newline = remaining.rfind("\n", 0, cut)
                space = remaining.rfind(" ", 0, cut)
                cut = max(newline, space, 1)
            chunk = _safe(remaining[:cut].rstrip()) or " "
            if len(chunk) > TELEGRAM_TEXT_LIMIT:
                chunk = chunk[:TELEGRAM_TEXT_LIMIT]
            chunks.append(RenderedMessage(chunk))
            remaining = remaining[cut:].lstrip()
        return tuple(chunks)
