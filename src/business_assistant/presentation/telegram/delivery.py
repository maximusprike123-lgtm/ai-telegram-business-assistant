"""All Telegram Bot API delivery is isolated behind this gateway."""

from uuid import UUID

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
)

from business_assistant.domain.shared import TenantId

from .callbacks import SignedCallbackCodec
from .models import RenderedMessage

REPLY_MENU = (
    ("Services", "Business hours"),
    ("Privacy", "Human help"),
    ("Help", "Cancel"),
)


class AiogramDeliveryGateway:
    def __init__(self, bot: Bot, codec: SignedCallbackCodec) -> None:
        self._bot = bot
        self._codec = codec

    def _inline_markup(
        self, tenant_id: TenantId, page: RenderedMessage
    ) -> InlineKeyboardMarkup | None:
        if not page.button_rows:
            return None
        rows = []
        for row in page.button_rows[:8]:
            buttons = []
            for button in row[:2]:
                entity_id = UUID(button.entity_id) if button.entity_id is not None else None
                buttons.append(
                    InlineKeyboardButton(
                        text=button.label,
                        callback_data=self._codec.encode(
                            tenant_id, button.action, entity_id, button.page
                        ),
                    )
                )
            rows.append(buttons)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @staticmethod
    def _reply_markup() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label) for label in row] for row in REPLY_MENU],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Choose an option or type a command",
        )

    async def send(self, chat_id: int, tenant_id: TenantId, page: RenderedMessage) -> Message:
        markup = (
            self._reply_markup() if page.show_reply_menu else self._inline_markup(tenant_id, page)
        )
        return await self._bot.send_message(
            chat_id,
            page.text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def replace_or_send(
        self, callback: CallbackQuery, tenant_id: TenantId, page: RenderedMessage
    ) -> None:
        markup = self._inline_markup(tenant_id, page)
        message = callback.message
        if isinstance(message, Message) and not page.show_reply_menu:
            try:
                await self._bot.edit_message_text(
                    page.text,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                return
            except TelegramBadRequest:
                pass
        if isinstance(message, Message):
            await self.send(message.chat.id, tenant_id, page)

    async def answer_callback(self, callback: CallbackQuery) -> None:
        try:
            await self._bot.answer_callback_query(callback.id)
        except TelegramBadRequest:
            # Telegram rejects answers for sufficiently old queries. The required answer was
            # attempted; navigation processing must not become retryable solely for that reason.
            return
