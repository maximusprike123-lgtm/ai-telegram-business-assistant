from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from business_assistant.domain.shared import ConversationId, CustomerId, Locale, TenantId


@dataclass(frozen=True, slots=True)
class TelegramBotBinding:
    bot_id: int
    tenant_id: TenantId

    def __post_init__(self) -> None:
        if self.bot_id <= 0:
            raise ValueError("Telegram bot ID must be positive")


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    tenant_id: TenantId
    customer_id: CustomerId
    conversation_id: ConversationId
    locale: Locale


class TelegramUpdateClaimResult(StrEnum):
    FIRST = "first"
    RETRY = "retry"
    DUPLICATE = "duplicate"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True, slots=True)
class TelegramUpdateClaim:
    result: TelegramUpdateClaimResult
    attempts: int
    claimed_at: datetime
