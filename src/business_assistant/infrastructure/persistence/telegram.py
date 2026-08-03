"""PostgreSQL adapters for Telegram identity and durable update processing."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import TelegramIdentityUnavailableError
from business_assistant.application.common.localization import locale_candidates
from business_assistant.application.telegram import (
    TelegramIdentity,
    TelegramUpdateClaim,
    TelegramUpdateClaimResult,
)
from business_assistant.domain.shared import ConversationId, CustomerId, Locale, TenantId

from .sqlalchemy.models import (
    ChannelIdentityRow,
    ConversationRow,
    CustomerRow,
    TelegramUpdateRow,
    TenantRow,
)


class SQLAlchemyTelegramIdentityStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(
        self,
        tenant_id: TenantId,
        *,
        external_user_id: str,
        external_chat_id: str,
        requested_locale: str | None,
        now: datetime,
    ) -> TelegramIdentity:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"telegram:{tenant_id}:{external_user_id}"},
            )
            tenant = await session.scalar(select(TenantRow).where(TenantRow.id == tenant_id.value))
            if tenant is None or tenant.status != "active":
                raise TelegramIdentityUnavailableError()
            supported = frozenset(Locale(value) for value in tenant.supported_locales)
            locale = locale_candidates(requested_locale, Locale(tenant.default_locale), supported)[
                0
            ]
            identity = await session.scalar(
                select(ChannelIdentityRow).where(
                    ChannelIdentityRow.tenant_id == tenant_id.value,
                    ChannelIdentityRow.channel == "telegram",
                    ChannelIdentityRow.external_user_id == external_user_id,
                )
            )
            if identity is None:
                customer_id = CustomerId.new()
                session.add(
                    CustomerRow(
                        id=customer_id.value,
                        tenant_id=tenant_id.value,
                        display_name=None,
                        phone_raw=None,
                        phone_e164=None,
                        phone_verified=False,
                        email=None,
                        locale=locale.value,
                        privacy_notice_version=None,
                        privacy_accepted_at=None,
                        contact_consent_at=None,
                        status="active",
                    )
                )
                await session.flush()
                identity = ChannelIdentityRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    customer_id=customer_id.value,
                    channel="telegram",
                    external_user_id=external_user_id,
                    external_chat_id=external_chat_id,
                )
                session.add(identity)
                await session.flush()
            else:
                customer_id = CustomerId(identity.customer_id)
                if identity.external_chat_id != external_chat_id:
                    identity.external_chat_id = external_chat_id

            conversation = await session.scalar(
                select(ConversationRow)
                .where(
                    ConversationRow.tenant_id == tenant_id.value,
                    ConversationRow.channel_identity_id == identity.id,
                    ConversationRow.status != "closed",
                )
                .order_by(ConversationRow.created_at.desc())
                .limit(1)
            )
            if conversation is None:
                conversation = ConversationRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    customer_id=customer_id.value,
                    channel_identity_id=identity.id,
                    status="active_bot",
                    locale=locale.value,
                    active_workflow=None,
                    last_message_at=now,
                    summary_version=0,
                )
                session.add(conversation)
            else:
                conversation.last_message_at = now
            return TelegramIdentity(tenant_id, customer_id, ConversationId(conversation.id), locale)


class SQLAlchemyTelegramUpdateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
        stale_after_seconds: int,
    ) -> TelegramUpdateClaim:
        async with self._session_factory() as session, session.begin():
            inserted = await session.scalar(
                insert(TelegramUpdateRow)
                .values(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    bot_id=bot_id,
                    update_id=update_id,
                    status="processing",
                    attempts=1,
                    claimed_at=now,
                    completed_at=None,
                    last_error_code=None,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "bot_id", "update_id"])
                .returning(TelegramUpdateRow.id)
            )
            if inserted is not None:
                return TelegramUpdateClaim(TelegramUpdateClaimResult.FIRST, 1, now)
            row = await session.scalar(
                select(TelegramUpdateRow)
                .where(
                    TelegramUpdateRow.tenant_id == tenant_id.value,
                    TelegramUpdateRow.bot_id == bot_id,
                    TelegramUpdateRow.update_id == update_id,
                )
                .with_for_update()
            )
            if row is None:
                raise RuntimeError("Telegram update claim disappeared")
            if row.status == "completed":
                return TelegramUpdateClaim(
                    TelegramUpdateClaimResult.DUPLICATE, row.attempts, row.claimed_at
                )
            stale_before = now - timedelta(seconds=stale_after_seconds)
            if row.status == "processing" and row.claimed_at > stale_before:
                return TelegramUpdateClaim(
                    TelegramUpdateClaimResult.IN_PROGRESS, row.attempts, row.claimed_at
                )
            row.status = "processing"
            row.attempts += 1
            row.claimed_at = now
            row.completed_at = None
            row.last_error_code = None
            return TelegramUpdateClaim(TelegramUpdateClaimResult.RETRY, row.attempts, now)

    async def complete(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(TelegramUpdateRow)
                .where(
                    TelegramUpdateRow.tenant_id == tenant_id.value,
                    TelegramUpdateRow.bot_id == bot_id,
                    TelegramUpdateRow.update_id == update_id,
                    TelegramUpdateRow.status == "processing",
                )
                .values(status="completed", completed_at=now, last_error_code=None)
            )

    async def fail(
        self,
        tenant_id: TenantId,
        *,
        bot_id: int,
        update_id: int,
        now: datetime,
        error_code: str,
    ) -> None:
        safe_code = (
            error_code if error_code.isascii() and len(error_code) <= 64 else "internal.error"
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(TelegramUpdateRow)
                .where(
                    TelegramUpdateRow.tenant_id == tenant_id.value,
                    TelegramUpdateRow.bot_id == bot_id,
                    TelegramUpdateRow.update_id == update_id,
                    TelegramUpdateRow.status == "processing",
                )
                .values(status="failed", completed_at=now, last_error_code=safe_code)
            )

    async def delete_completed_before(self, before: datetime) -> int:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                delete(TelegramUpdateRow).where(
                    TelegramUpdateRow.status.in_(("completed", "failed")),
                    TelegramUpdateRow.created_at < before,
                )
            )
            return int(getattr(result, "rowcount", 0) or 0)
