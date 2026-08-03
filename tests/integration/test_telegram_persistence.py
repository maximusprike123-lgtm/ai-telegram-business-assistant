import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import TelegramIdentityUnavailableError
from business_assistant.application.telegram import TelegramUpdateClaimResult
from business_assistant.domain.shared import Locale
from business_assistant.infrastructure.persistence import (
    SQLAlchemyTelegramIdentityStore,
    SQLAlchemyTelegramUpdateStore,
)
from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_TENANT_ID,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    ChannelIdentityRow,
    ConversationRow,
    CustomerRow,
    TelegramUpdateRow,
    TenantRow,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_update_claim_lifecycle_duplicate_failure_stale_retry_and_retention(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyTelegramUpdateStore(factory)
    now = datetime(2026, 8, 3, tzinfo=UTC)

    first = await store.claim(
        NORTHSTAR_TENANT_ID, bot_id=42, update_id=1, now=now, stale_after_seconds=60
    )
    assert first.result is TelegramUpdateClaimResult.FIRST
    in_progress = await store.claim(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(seconds=1),
        stale_after_seconds=60,
    )
    assert in_progress.result is TelegramUpdateClaimResult.IN_PROGRESS
    retry = await store.claim(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(seconds=61),
        stale_after_seconds=60,
    )
    assert retry.result is TelegramUpdateClaimResult.RETRY
    assert retry.attempts == 2
    await store.fail(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(seconds=62),
        error_code="delivery.unavailable",
    )
    failed_retry = await store.claim(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(seconds=63),
        stale_after_seconds=60,
    )
    assert failed_retry.result is TelegramUpdateClaimResult.RETRY
    await store.complete(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(seconds=64),
    )
    duplicate = await store.claim(
        NORTHSTAR_TENANT_ID,
        bot_id=42,
        update_id=1,
        now=now + timedelta(days=1),
        stale_after_seconds=60,
    )
    assert duplicate.result is TelegramUpdateClaimResult.DUPLICATE

    async with factory() as session, session.begin():
        await session.execute(
            update(TelegramUpdateRow)
            .where(TelegramUpdateRow.update_id == 1)
            .values(created_at=now - timedelta(days=8))
        )
    assert await store.delete_completed_before(now - timedelta(days=7)) == 1


@pytest.mark.asyncio
async def test_concurrent_update_claim_has_one_owner(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyTelegramUpdateStore(factory)
    now = datetime(2026, 8, 3, tzinfo=UTC)
    claims = await asyncio.gather(
        *(
            store.claim(
                NORTHSTAR_TENANT_ID,
                bot_id=42,
                update_id=99,
                now=now,
                stale_after_seconds=60,
            )
            for _ in range(8)
        )
    )
    results = [claim.result for claim in claims]
    assert results.count(TelegramUpdateClaimResult.FIRST) == 1
    assert results.count(TelegramUpdateClaimResult.IN_PROGRESS) == 7


@pytest.mark.asyncio
async def test_identity_resolution_is_minimal_english_and_concurrency_safe(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyTelegramIdentityStore(factory)
    now = datetime(2026, 8, 3, tzinfo=UTC)
    identities = await asyncio.gather(
        *(
            store.resolve(
                NORTHSTAR_TENANT_ID,
                external_user_id="123456",
                external_chat_id="123456",
                requested_locale="fr",
                now=now,
            )
            for _ in range(6)
        )
    )
    assert {identity.customer_id for identity in identities} == {identities[0].customer_id}
    assert {identity.conversation_id for identity in identities} == {identities[0].conversation_id}
    assert all(identity.locale is Locale.EN for identity in identities)
    async with factory() as session:
        customers = await session.scalar(select(func.count()).select_from(CustomerRow))
        channel_identities = await session.scalar(
            select(func.count()).select_from(ChannelIdentityRow)
        )
        conversations = await session.scalar(select(func.count()).select_from(ConversationRow))
        customer = await session.scalar(select(CustomerRow))
    assert customers == channel_identities == conversations == 1
    assert customer is not None
    assert customer.display_name is None
    assert customer.email is None
    assert customer.phone_raw is None
    assert customer.locale == "en"

    changed_chat = await store.resolve(
        NORTHSTAR_TENANT_ID,
        external_user_id="123456",
        external_chat_id="654321",
        requested_locale="en",
        now=now + timedelta(minutes=1),
    )
    assert changed_chat.conversation_id == identities[0].conversation_id
    async with factory() as session:
        channel = await session.scalar(select(ChannelIdentityRow))
    assert channel is not None and channel.external_chat_id == "654321"

    async with factory() as session, session.begin():
        await session.execute(
            update(TenantRow)
            .where(TenantRow.id == NORTHSTAR_TENANT_ID.value)
            .values(status="inactive")
        )
    with pytest.raises(TelegramIdentityUnavailableError):
        await store.resolve(
            NORTHSTAR_TENANT_ID,
            external_user_id="999999",
            external_chat_id="999999",
            requested_locale="en",
            now=now,
        )
