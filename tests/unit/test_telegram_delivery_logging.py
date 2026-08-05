import json
import logging
from datetime import UTC, datetime

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery
from tests.unit.test_telegram_dispatcher import FakeSession, FixedClock

from business_assistant.domain.shared import TenantId
from business_assistant.infrastructure.observability.logging import (
    SafeJsonFormatter,
    configure_logging,
)
from business_assistant.presentation.telegram import (
    AiogramDeliveryGateway,
    CallbackAction,
    SignedCallbackCodec,
)
from business_assistant.presentation.telegram.models import NavigationButton, RenderedMessage


@pytest.mark.asyncio
async def test_delivery_gateway_builds_bounded_reply_and_inline_keyboards() -> None:
    session = FakeSession()
    bot = Bot("42:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    tenant_id = TenantId.new()
    codec = SignedCallbackCodec(
        "delivery-callback-key",  # pragma: allowlist secret
        version=1,
        expiry_seconds=60,
        clock=FixedClock(),
    )
    gateway = AiogramDeliveryGateway(bot, codec)
    await gateway.send(100, tenant_id, RenderedMessage("home", show_reply_menu=True))
    method = session.methods[-1]
    assert isinstance(method, SendMessage)
    assert method.reply_markup is not None

    page = RenderedMessage(
        "catalog",
        ((NavigationButton("Home", CallbackAction.HOME),),),
    )
    await gateway.send(100, tenant_id, page)
    method = session.methods[-1]
    assert isinstance(method, SendMessage)
    assert method.reply_markup is not None
    callback_data = method.reply_markup.inline_keyboard[0][0].callback_data
    assert callback_data is not None
    assert codec.decode(tenant_id, callback_data).action is CallbackAction.HOME


class EditFailsOnceSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, EditMessageText) and not self.failed:
            self.failed = True
            raise TelegramBadRequest(method, "message is not modified")
        return True


@pytest.mark.asyncio
async def test_callback_delivery_falls_back_to_send_when_edit_is_unavailable() -> None:
    session = EditFailsOnceSession()
    bot = Bot("42:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    tenant_id = TenantId.new()
    codec = SignedCallbackCodec(
        "delivery-callback-key",  # pragma: allowlist secret
        version=1,
        expiry_seconds=60,
        clock=FixedClock(),
    )
    callback = CallbackQuery.model_validate(
        {
            "id": "callback",
            "from": {"id": 100, "is_bot": False, "first_name": "Ignored"},
            "chat_instance": "instance",
            "message": {
                "message_id": 1,
                "date": int(datetime(2026, 8, 3, tzinfo=UTC).timestamp()),
                "chat": {"id": 100, "type": "private"},
            },
        },
        context={"bot": bot},
    )
    gateway = AiogramDeliveryGateway(bot, codec)
    await gateway.replace_or_send(
        callback,
        tenant_id,
        RenderedMessage("replacement", ((NavigationButton("Home", CallbackAction.HOME),),)),
    )
    assert isinstance(session.methods[-2], EditMessageText)
    assert isinstance(session.methods[-1], SendMessage)
    await gateway.answer_callback(callback)
    assert session.methods[-1].__class__.__name__ == "AnswerCallbackQuery"


def test_safe_json_formatter_allowlists_context_and_drops_exception_details() -> None:
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "telegram.update.failed",
        (),
        RuntimeError("raw message body and secret"),
    )
    record.safe_context = {
        "tenant_id": "tenant",
        "update_id": 7,
        "message_text": "must not appear",
        "token": "must not appear",
        "phone": "+1-555-0100",
        "email": "customer@example.test",
        "records_affected": 3,
    }
    output = SafeJsonFormatter().format(record)
    parsed = json.loads(output)
    assert parsed["tenant_id"] == "tenant"
    assert parsed["update_id"] == 7
    assert "message_text" not in output
    assert "secret" not in output
    assert parsed["records_affected"] == 3
    assert "customer@example.test" not in output


def test_logging_configuration_supports_json_and_text_without_propagation() -> None:
    json_logger = configure_logging("INFO", "json")
    assert isinstance(json_logger.handlers[0].formatter, SafeJsonFormatter)
    assert not json_logger.propagate
    text_logger = configure_logging("WARNING", "text")
    assert text_logger.level == logging.WARNING
    assert not isinstance(text_logger.handlers[0].formatter, SafeJsonFormatter)
