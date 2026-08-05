"""Telegram staff-notification adapter with classified provider failures."""

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from business_assistant.application.background import (
    DeliveryClaim,
    NotificationDeliveryError,
)


class TelegramNotificationGateway:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send(self, claim: DeliveryClaim, *, text: str) -> None:
        try:
            await self._bot.send_message(int(claim.recipient_id), text)
        except TelegramRetryAfter as exc:
            raise NotificationDeliveryError("telegram.rate_limited", retryable=True) from exc
        except TelegramNetworkError as exc:
            raise NotificationDeliveryError("telegram.network", retryable=True) from exc
        except TelegramForbiddenError as exc:
            raise NotificationDeliveryError("telegram.forbidden", retryable=False) from exc
        except TelegramBadRequest as exc:
            raise NotificationDeliveryError("telegram.bad_request", retryable=False) from exc
