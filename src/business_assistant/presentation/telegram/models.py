from dataclasses import dataclass

from .callbacks import CallbackAction


@dataclass(frozen=True, slots=True)
class NavigationButton:
    label: str
    action: CallbackAction
    entity_id: str | None = None
    page: int | None = None


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    text: str
    button_rows: tuple[tuple[NavigationButton, ...], ...] = ()
    show_reply_menu: bool = False
