"""Safe correlation, update lifecycle, tenant binding, and identity middleware."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import TelegramObject, Update
from aiogram.types.update import UpdateTypeLookupError

from business_assistant.application.common.errors import ApplicationError
from business_assistant.application.common.ports import Clock
from business_assistant.application.telegram import (
    ResolveTelegramIdentity,
    TelegramBotBinding,
    TelegramUpdateClaimResult,
    TelegramUpdateStore,
)

NextHandler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class CorrelationMiddleware(BaseMiddleware):
    async def __call__(
        self, handler: NextHandler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        supplied = data.get("correlation_id")
        data["correlation_id"] = (
            supplied
            if isinstance(supplied, str) and supplied.isascii() and 1 <= len(supplied) <= 128
            else str(uuid4())
        )
        return await handler(event, data)


class UpdateDeduplicationMiddleware(BaseMiddleware):
    def __init__(
        self,
        store: TelegramUpdateStore,
        clock: Clock,
        binding: TelegramBotBinding,
        *,
        stale_after_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self._store = store
        self._clock = clock
        self._binding = binding
        self._stale_after_seconds = stale_after_seconds
        self._logger = logger

    async def __call__(
        self, handler: NextHandler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        bot = data.get("bot")
        if not isinstance(bot, Bot) or bot.id != self._binding.bot_id:
            raise RuntimeError("Configured Telegram bot does not match the trusted binding")
        now = self._clock.now()
        claim = await self._store.claim(
            self._binding.tenant_id,
            bot_id=self._binding.bot_id,
            update_id=event.update_id,
            now=now,
            stale_after_seconds=self._stale_after_seconds,
        )
        try:
            event_type = event.event_type
        except UpdateTypeLookupError:
            event_type = "unknown"
        context = {
            "correlation_id": data["correlation_id"],
            "tenant_id": str(self._binding.tenant_id),
            "bot_id": self._binding.bot_id,
            "update_id": event.update_id,
            "event_type": event_type,
            "claim_result": claim.result.value,
        }
        self._logger.info("telegram.update.claimed", extra={"safe_context": context})
        if claim.result in {
            TelegramUpdateClaimResult.DUPLICATE,
            TelegramUpdateClaimResult.IN_PROGRESS,
        }:
            return claim.result.value
        if event_type == "unknown":
            await self._store.complete(
                self._binding.tenant_id,
                bot_id=self._binding.bot_id,
                update_id=event.update_id,
                now=self._clock.now(),
            )
            self._logger.info("telegram.update.completed", extra={"safe_context": context})
            return "processed"
        try:
            await handler(event, data)
        except Exception as exc:
            code = exc.code if isinstance(exc, ApplicationError) else "internal.error"
            await self._store.fail(
                self._binding.tenant_id,
                bot_id=self._binding.bot_id,
                update_id=event.update_id,
                now=self._clock.now(),
                error_code=code,
            )
            self._logger.error(
                "telegram.update.failed",
                extra={
                    "safe_context": {
                        **context,
                        "error_code": code,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise
        await self._store.complete(
            self._binding.tenant_id,
            bot_id=self._binding.bot_id,
            update_id=event.update_id,
            now=self._clock.now(),
        )
        self._logger.info("telegram.update.completed", extra={"safe_context": context})
        return "processed"


class TelegramIdentityMiddleware(BaseMiddleware):
    def __init__(self, resolver: ResolveTelegramIdentity, binding: TelegramBotBinding) -> None:
        self._resolver = resolver
        self._binding = binding

    async def __call__(
        self, handler: NextHandler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        message = event.message
        callback = event.callback_query
        user = (
            message.from_user if message is not None else callback.from_user if callback else None
        )
        chat = (
            message.chat
            if message is not None
            else callback.message.chat
            if callback and callback.message
            else None
        )
        if user is not None and chat is not None and chat.type == ChatType.PRIVATE:
            data["telegram_identity"] = await self._resolver.execute(
                self._binding.tenant_id,
                external_user_id=user.id,
                external_chat_id=chat.id,
                requested_locale=user.language_code,
            )
        return await handler(event, data)
