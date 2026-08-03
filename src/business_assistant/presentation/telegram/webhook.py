"""FastAPI webhook boundary for authenticated, bounded aiogram updates."""

import hmac
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from business_assistant.application.telegram import TelegramBotBinding


@dataclass(frozen=True, slots=True)
class TelegramWebhookServices:
    dispatcher: Dispatcher
    bot: Bot
    binding: TelegramBotBinding
    webhook_secret: str
    path_secret: str
    update_max_bytes: int
    logger: logging.Logger


def _error(status: int, code: str, message: str, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "correlation_id": correlation_id},
    )


def install_telegram_webhook(app: FastAPI, services: TelegramWebhookServices) -> None:
    @app.post(
        "/api/v1/webhooks/telegram/{path_secret}",
        tags=["Telegram"],
        summary="Receive an authenticated Telegram update",
        include_in_schema=True,
    )
    async def telegram_webhook(
        path_secret: str,
        request: Request,
        telegram_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
    ) -> JSONResponse:
        correlation_id = str(getattr(request.state, "correlation_id", "unknown"))
        if telegram_secret is None or not hmac.compare_digest(
            telegram_secret, services.webhook_secret
        ):
            return _error(
                401,
                "telegram.webhook_authentication_failed",
                "Webhook authentication failed",
                correlation_id,
            )
        if not hmac.compare_digest(path_secret, services.path_secret):
            return _error(
                404,
                "telegram.bot_mapping_not_found",
                "Telegram bot mapping was not found",
                correlation_id,
            )
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _error(
                415,
                "telegram.content_type_invalid",
                "Content-Type must be application/json",
                correlation_id,
            )
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
                if parsed_length < 0:
                    raise ValueError
                if parsed_length > services.update_max_bytes:
                    return _error(
                        413,
                        "telegram.update_too_large",
                        "Telegram update exceeds the allowed size",
                        correlation_id,
                    )
            except ValueError:
                return _error(
                    400,
                    "telegram.content_length_invalid",
                    "Content-Length is invalid",
                    correlation_id,
                )
        chunks: list[bytes] = []
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > services.update_max_bytes:
                return _error(
                    413,
                    "telegram.update_too_large",
                    "Telegram update exceeds the allowed size",
                    correlation_id,
                )
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            update = Update.model_validate_json(body, context={"bot": services.bot})
        except ValidationError:
            return _error(
                400,
                "telegram.update_invalid",
                "Telegram update schema is invalid",
                correlation_id,
            )
        try:
            result = await services.dispatcher.feed_update(
                services.bot, update, correlation_id=correlation_id
            )
        except Exception as exc:
            services.logger.error(
                "telegram.webhook.processing_failed",
                extra={
                    "safe_context": {
                        "correlation_id": correlation_id,
                        "tenant_id": str(services.binding.tenant_id),
                        "bot_id": services.binding.bot_id,
                        "update_id": update.update_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            return _error(
                503,
                "telegram.processing_unavailable",
                "Telegram update processing is temporarily unavailable",
                correlation_id,
            )
        return JSONResponse(status_code=200, content={"status": str(result)})
