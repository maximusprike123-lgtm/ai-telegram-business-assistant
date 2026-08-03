"""Aiogram 3 dispatcher, routers, and thin Telegram handlers."""

import logging
from dataclasses import dataclass

from aiogram import Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from business_assistant.application.common.errors import ApplicationError
from business_assistant.application.common.ports import Clock
from business_assistant.application.telegram import (
    ResolveTelegramIdentity,
    TelegramBotBinding,
    TelegramIdentity,
    TelegramUpdateStore,
)
from business_assistant.domain.shared import CategoryId, ServiceId

from .callbacks import CallbackAction, CallbackTokenError, SignedCallbackCodec
from .delivery import AiogramDeliveryGateway
from .middleware import (
    CorrelationMiddleware,
    TelegramIdentityMiddleware,
    UpdateDeduplicationMiddleware,
)
from .navigation import TelegramNavigation
from .renderer import TelegramRenderer


@dataclass(frozen=True, slots=True)
class TelegramRuntime:
    binding: TelegramBotBinding
    navigation: TelegramNavigation
    renderer: TelegramRenderer
    delivery: AiogramDeliveryGateway
    callbacks: SignedCallbackCodec
    identity_resolver: ResolveTelegramIdentity
    update_store: TelegramUpdateStore
    clock: Clock
    processing_stale_seconds: int
    logger: logging.Logger


def build_dispatcher(runtime: TelegramRuntime) -> Dispatcher:
    dispatcher = Dispatcher(disable_fsm=True)
    router = Router(name="phase4-private")
    private = F.chat.type == ChatType.PRIVATE

    async def send_page(message: Message, identity: TelegramIdentity, page_name: str) -> None:
        if page_name == "home":
            page = await runtime.navigation.home(identity)
        elif page_name == "catalog":
            page = await runtime.navigation.catalog(identity)
        elif page_name == "hours":
            page = await runtime.navigation.hours(identity)
        elif page_name == "privacy":
            page = runtime.renderer.privacy()
        elif page_name == "human":
            page = runtime.renderer.human_placeholder()
        elif page_name == "cancel":
            page = runtime.renderer.cancelled()
        elif page_name == "help":
            page = runtime.renderer.help()
        else:
            page = runtime.renderer.unknown()
        await runtime.delivery.send(message.chat.id, identity.tenant_id, page)

    @router.message(Command("start"), private)
    async def start(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "home")

    @router.message(Command("help"), private)
    async def help_command(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "help")

    @router.message(Command("catalog"), private)
    async def catalog_command(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "catalog")

    @router.message(Command("hours"), private)
    async def hours_command(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "hours")

    @router.message(Command("cancel"), private)
    async def cancel_command(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "cancel")

    @router.message(F.text == "Services", private)
    async def services_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "catalog")

    @router.message(F.text == "Business hours", private)
    async def hours_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "hours")

    @router.message(F.text == "Privacy", private)
    async def privacy_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "privacy")

    @router.message(F.text == "Human help", private)
    async def human_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "human")

    @router.message(F.text == "Help", private)
    async def help_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "help")

    @router.message(F.text == "Cancel", private)
    async def cancel_button(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "cancel")

    @router.callback_query()
    async def callback_handler(
        callback: CallbackQuery, telegram_identity: TelegramIdentity | None = None
    ) -> None:
        try:
            if telegram_identity is None or callback.data is None:
                return
            try:
                token = runtime.callbacks.decode(telegram_identity.tenant_id, callback.data)
                if token.action is CallbackAction.HOME:
                    page = await runtime.navigation.home(telegram_identity)
                elif token.action is CallbackAction.CATALOG:
                    page = await runtime.navigation.catalog(telegram_identity, token.page or 0)
                elif token.action is CallbackAction.CATEGORY and token.entity_id is not None:
                    page = await runtime.navigation.category(
                        telegram_identity, CategoryId(token.entity_id), token.page or 0
                    )
                elif token.action is CallbackAction.SERVICE and token.entity_id is not None:
                    page = await runtime.navigation.service(
                        telegram_identity, ServiceId(token.entity_id)
                    )
                elif token.action is CallbackAction.HOURS:
                    page = await runtime.navigation.hours(telegram_identity)
                elif token.action is CallbackAction.PRIVACY:
                    page = runtime.renderer.privacy()
                elif token.action is CallbackAction.HUMAN:
                    page = runtime.renderer.human_placeholder()
                elif token.action is CallbackAction.CANCEL:
                    page = runtime.renderer.cancelled()
                else:
                    page = runtime.renderer.callback_recovery()
            except (CallbackTokenError, ApplicationError, ValueError):
                page = runtime.renderer.callback_recovery()
            await runtime.delivery.replace_or_send(callback, telegram_identity.tenant_id, page)
        finally:
            await runtime.delivery.answer_callback(callback)

    @router.message(private)
    async def unknown_message(message: Message, telegram_identity: TelegramIdentity) -> None:
        await send_page(message, telegram_identity, "unknown")

    dispatcher.update.outer_middleware(CorrelationMiddleware())
    dispatcher.update.outer_middleware(
        UpdateDeduplicationMiddleware(
            runtime.update_store,
            runtime.clock,
            runtime.binding,
            stale_after_seconds=runtime.processing_stale_seconds,
            logger=runtime.logger,
        )
    )
    dispatcher.update.outer_middleware(
        TelegramIdentityMiddleware(runtime.identity_resolver, runtime.binding)
    )
    dispatcher.include_router(router)
    return dispatcher
