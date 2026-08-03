from business_assistant.application.common.ports import Clock
from business_assistant.domain.shared import TenantId, ValidationError

from .models import TelegramIdentity
from .ports import TelegramIdentityStore


class ResolveTelegramIdentity:
    def __init__(self, store: TelegramIdentityStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def execute(
        self,
        tenant_id: TenantId,
        *,
        external_user_id: int,
        external_chat_id: int,
        requested_locale: str | None,
    ) -> TelegramIdentity:
        if external_user_id <= 0:
            raise ValidationError("Telegram user ID must be positive")
        if external_chat_id == 0:
            raise ValidationError("Telegram chat ID must be nonzero")
        return await self._store.resolve(
            tenant_id,
            external_user_id=str(external_user_id),
            external_chat_id=str(external_chat_id),
            requested_locale=requested_locale,
            now=self._clock.now(),
        )
