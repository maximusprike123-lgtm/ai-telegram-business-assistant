import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods.base import TelegramMethod, TelegramType

from business_assistant.application.handoffs import HandoffView
from business_assistant.application.telegram import (
    TelegramBotBinding,
    TelegramIdentity,
    TelegramUpdateClaim,
    TelegramUpdateClaimResult,
)
from business_assistant.domain.shared import (
    ConversationId,
    CustomerId,
    HandoffId,
    Locale,
    TenantId,
)
from business_assistant.presentation.telegram import (
    CallbackAction,
    SignedCallbackCodec,
    TelegramRenderer,
    TelegramRuntime,
    build_dispatcher,
)
from business_assistant.presentation.telegram.models import RenderedMessage


class FixedClock:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 3, tzinfo=UTC)

    def now(self) -> datetime:
        return self.instant


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        self.methods.append(method)
        return True  # type: ignore[return-value]

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65_536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:
            yield b""


class FakeUpdateStore:
    def __init__(self) -> None:
        self.completed: set[tuple[int, int]] = set()
        self.failed: list[str] = []

    async def claim(self, tenant_id, *, bot_id, update_id, now, stale_after_seconds):
        key = (bot_id, update_id)
        result = (
            TelegramUpdateClaimResult.DUPLICATE
            if key in self.completed
            else TelegramUpdateClaimResult.FIRST
        )
        return TelegramUpdateClaim(result, 1, now)

    async def complete(self, tenant_id, *, bot_id, update_id, now) -> None:
        self.completed.add((bot_id, update_id))

    async def fail(self, tenant_id, *, bot_id, update_id, now, error_code) -> None:
        self.failed.append(error_code)

    async def delete_completed_before(self, before) -> int:
        return 0


class FakeIdentityResolver:
    def __init__(self, identity: TelegramIdentity) -> None:
        self.identity = identity
        self.calls = 0

    async def execute(self, tenant_id, **kwargs):
        self.calls += 1
        return self.identity


class FakeNavigation:
    paused_result: HandoffView | None = None

    async def paused(self, identity):
        return self.paused_result

    async def home(self, identity):
        return RenderedMessage("home", show_reply_menu=True)

    async def catalog(self, identity):
        return RenderedMessage("catalog")

    async def hours(self, identity):
        return RenderedMessage("hours")

    async def category(self, identity, category_id):
        return RenderedMessage(f"category:{category_id}")

    async def service(self, identity, service_id):
        return RenderedMessage(f"service:{service_id}")

    async def cancel_flow(self, identity):
        return RenderedMessage("no active workflow")

    async def booking_text(self, identity, value):
        return None

    async def qualification_text(self, identity, value, update_key):
        return None

    async def unsupported(self, identity, *, update_key):
        return TelegramRenderer().unknown()

    async def route_free_text(self, identity, text, *, update_key):
        return await self.unsupported(identity, update_key=update_key)

    async def human_help(self, identity, *, update_key):
        return TelegramRenderer().human_placeholder()


class FakeDelivery:
    def __init__(self) -> None:
        self.sent: list[RenderedMessage] = []
        self.replaced: list[RenderedMessage] = []
        self.answered_callbacks = 0

    async def send(self, chat_id, tenant_id, page):
        self.sent.append(page)
        return None

    async def replace_or_send(self, callback, tenant_id, page) -> None:
        self.replaced.append(page)

    async def answer_callback(self, callback) -> None:
        self.answered_callbacks += 1


def private_message(update_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_775_000_000,
            "text": text,
            "chat": {"id": 100, "type": "private"},
            "from": {
                "id": 100,
                "is_bot": False,
                "first_name": "Ignored",
                "language_code": "fr",
            },
        },
    }


def runtime_fixture():
    clock = FixedClock()
    tenant_id = TenantId.new()
    identity = TelegramIdentity(tenant_id, CustomerId.new(), ConversationId.new(), Locale.EN)
    session = FakeSession()
    bot = Bot("42:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    store = FakeUpdateStore()
    resolver = FakeIdentityResolver(identity)
    delivery = FakeDelivery()
    renderer = TelegramRenderer()
    codec = SignedCallbackCodec(
        "dispatcher-callback-key",  # pragma: allowlist secret
        version=1,
        expiry_seconds=60,
        clock=clock,
    )
    runtime = TelegramRuntime(
        TelegramBotBinding(42, tenant_id),
        FakeNavigation(),  # type: ignore[arg-type]
        renderer,
        delivery,  # type: ignore[arg-type]
        codec,
        resolver,  # type: ignore[arg-type]
        store,
        clock,
        60,
        logging.getLogger("test.telegram"),
    )
    return bot, session, store, resolver, delivery, codec, identity, build_dispatcher(runtime)


@pytest.mark.asyncio
async def test_commands_unknown_text_and_duplicate_update_use_the_same_pipeline() -> None:
    bot, _, store, resolver, delivery, _, _, dispatcher = runtime_fixture()
    result = await dispatcher.feed_raw_update(bot, private_message(1, "/start"))
    assert result == "processed"
    assert delivery.sent[-1].text == "home"
    assert resolver.calls == 1

    duplicate = await dispatcher.feed_raw_update(bot, private_message(1, "/start"))
    assert duplicate == "duplicate"
    assert len(delivery.sent) == 1

    for update_id, text, expected in (
        (2, "/help", "Help"),
        (3, "/catalog", "catalog"),
        (4, "/hours", "hours"),
        (5, "/cancel", "no active workflow"),
        (6, "/language", "AI and free-form"),
        (7, "unstructured question", "AI and free-form"),
        (8, "Privacy", "Privacy notice"),
        (9, "Human help", "No request has been created"),
    ):
        result = await dispatcher.feed_raw_update(bot, private_message(update_id, text))
        assert result == "processed"
        assert expected in delivery.sent[-1].text
    assert not store.failed


@pytest.mark.asyncio
async def test_unsupported_group_is_quiet_and_does_not_create_identity() -> None:
    bot, _, _, resolver, delivery, _, _, dispatcher = runtime_fixture()
    update = private_message(10, "/start")
    update["message"]["chat"] = {"id": -1001, "type": "group"}
    assert await dispatcher.feed_raw_update(bot, update) == "processed"
    assert resolver.calls == 0
    assert delivery.sent == []

    assert await dispatcher.feed_raw_update(bot, {"update_id": 11}) == "processed"
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_valid_repeated_and_malformed_callbacks_are_answered_with_recovery() -> None:
    bot, _, _, _, delivery, codec, identity, dispatcher = runtime_fixture()
    token = codec.encode(identity.tenant_id, CallbackAction.HOME)

    def callback_update(update_id: int, data: str) -> dict[str, Any]:
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"callback-{update_id}",
                "from": {"id": 100, "is_bot": False, "first_name": "Ignored"},
                "chat_instance": "instance",
                "data": data,
                "message": {
                    "message_id": 5,
                    "date": 1_775_000_000,
                    "chat": {"id": 100, "type": "private"},
                },
            },
        }

    assert await dispatcher.feed_raw_update(bot, callback_update(20, token)) == "processed"
    assert delivery.replaced[-1].text == "home"
    assert await dispatcher.feed_raw_update(bot, callback_update(21, token)) == "processed"
    assert delivery.replaced[-1].text == "home"
    assert await dispatcher.feed_raw_update(bot, callback_update(22, "malformed")) == "processed"
    assert "no longer valid" in delivery.replaced[-1].text
    assert delivery.answered_callbacks == 3


@pytest.mark.asyncio
async def test_active_handoff_pauses_command_callback_and_free_text_routing() -> None:
    bot, _, _, _, delivery, codec, identity, dispatcher = runtime_fixture()
    FakeNavigation.paused_result = HandoffView(
        HandoffId.new(),
        identity.tenant_id,
        identity.customer_id,
        identity.conversation_id,
        None,
        "explicit_manager_request",
        "normal",
        "queued",
        "Customer requested a person.",
        {"timezone": "UTC"},
        datetime(2026, 8, 4, 14, tzinfo=UTC),
        None,
    )
    try:
        await dispatcher.feed_raw_update(bot, private_message(30, "/catalog"))
        await dispatcher.feed_raw_update(bot, private_message(31, "more details"))
        assert all("Bot replies are paused" in item.text for item in delivery.sent[-2:])

        token = codec.encode(identity.tenant_id, CallbackAction.HOME)
        update = {
            "update_id": 32,
            "callback_query": {
                "id": "callback-32",
                "from": {"id": 100, "is_bot": False, "first_name": "Ignored"},
                "chat_instance": "instance",
                "data": token,
                "message": {
                    "message_id": 5,
                    "date": 1_775_000_000,
                    "chat": {"id": 100, "type": "private"},
                },
            },
        }
        await dispatcher.feed_raw_update(bot, update)
        assert "Bot replies are paused" in delivery.replaced[-1].text
    finally:
        FakeNavigation.paused_result = None
