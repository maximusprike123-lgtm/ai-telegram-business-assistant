from datetime import datetime
from typing import Protocol

from business_assistant.domain.shared import TenantId

from .models import TelegramIdentity, TelegramUpdateClaim


class TelegramIdentityStore(Protocol):
    async def resolve(
        self,
        tenant_id: TenantId,
        *,
        external_user_id: str,
        external_chat_id: str,
        requested_locale: str | None,
        now: datetime,
    ) -> TelegramIdentity: ...


class TelegramUpdateStore(Protocol):
    async def claim(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
        stale_after_seconds: int,
    ) -> TelegramUpdateClaim: ...

    async def complete(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
    ) -> None: ...

    async def fail(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
        error_code: str,
    ) -> None: ...

    async def delete_completed_before(self, before: datetime) -> int: ...
