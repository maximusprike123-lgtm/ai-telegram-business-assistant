"""English-only, HTML-safe Telegram rendering with explicit platform limits."""

from html import escape

from business_assistant.application.catalog import ServiceCategoryDTO, ServiceDTO
from business_assistant.application.scheduling import (
    BusinessDayDTO,
    BusinessStatusDTO,
    NextOpeningDTO,
)
from business_assistant.application.tenants import TenantPublicProfileDTO

from .callbacks import CallbackAction
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
        text = (
            f"<b>{_safe(profile.name)}</b>\n"
            f"{_safe(profile.description)}\n\n"
            f"<b>{status}</b> · {_safe(profile.status.local_time)} "
            f"({_safe(profile.timezone)})\n"
            f"{contact_block}\n"
            "This is a fictional portfolio demo. It can show verified business information, "
            "but AI and appointment booking are not enabled. It stores only numeric Telegram "
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
            "Appointment booking will be available in a later demo phase."
            if service.bookable
            else "This service is not available for booking."
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
        return RenderedMessage(
            "<b>Help</b>\nUse /catalog for services, /hours for opening times, /cancel "
            "to clear navigation, or the menu below. Free-form questions receive a safe, "
            "deterministic reply because AI is not enabled.",
            ((_button("Home", CallbackAction.HOME),),),
            show_reply_menu=True,
        )

    def privacy(self) -> RenderedMessage:
        return RenderedMessage(
            "<b>Privacy notice · demo-v1</b>\nThis fictional demo stores Telegram numeric user "
            "and chat identifiers to keep a tenant-scoped conversation and prevent duplicate "
            "updates. It does not store message bodies, usernames, profile names, or raw updates. "
            "Do not send sensitive or real customer information.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def human_placeholder(self) -> RenderedMessage:
        return RenderedMessage(
            "Human handoff is not enabled in this demo phase. No request has been created. "
            "Use the verified contact details on the home screen if you need assistance.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def cancelled(self) -> RenderedMessage:
        return RenderedMessage(
            "There is no active workflow or appointment hold to cancel. Navigation was reset.",
            ((_button("Home", CallbackAction.HOME),),),
        )

    def unknown(self) -> RenderedMessage:
        return RenderedMessage(
            "I can currently show verified services and business hours only. Use /catalog, "
            "/hours, /help, or the menu. AI, booking, and free-form business answers are not "
            "enabled in this phase.",
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
