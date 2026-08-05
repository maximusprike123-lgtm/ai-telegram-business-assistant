import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.background import (
    NotificationChannel,
    NotificationSubscription,
)
from business_assistant.application.observability import correlation_scope
from business_assistant.infrastructure.persistence import SQLAlchemyBackgroundStore
from business_assistant.infrastructure.persistence.seed import NORTHSTAR_TENANT_ID, seed_northstar
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    NotificationDeliveryRow,
    OutboxEventRow,
)

pytestmark = pytest.mark.postgresql
NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_outbox_projection_is_idempotent_and_tenant_scoped(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyBackgroundStore(factory)
    subscription = NotificationSubscription(
        uuid4(),
        NORTHSTAR_TENANT_ID,
        NotificationChannel.TELEGRAM,
        "123456",
        frozenset({"lead.qualified"}),
    )
    await store.save_subscription(subscription)
    replaced = await store.save_subscription(
        NotificationSubscription(
            uuid4(),
            NORTHSTAR_TENANT_ID,
            NotificationChannel.TELEGRAM,
            "123456",
            frozenset({"lead.qualified"}),
        )
    )
    assert replaced.id == subscription.id
    event_id = uuid4()
    with correlation_scope("phase11-correlation"):
        async with factory() as session, session.begin():
            session.add(
                OutboxEventRow(
                    id=uuid4(),
                    event_id=event_id,
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    aggregate_type="lead",
                    aggregate_id=uuid4(),
                    event_type="lead.qualified",
                    event_version=1,
                    payload={"lead_id": str(uuid4()), "priority": "high"},
                    status="pending",
                    attempts=0,
                    available_at=NOW,
                    occurred_at=NOW,
                )
            )

    assert await store.dispatch_outbox(now=NOW, limit=10, lease_seconds=60, max_attempts=6) == (
        1,
        1,
        0,
    )
    assert await store.dispatch_outbox(now=NOW, limit=10, lease_seconds=60, max_attempts=6) == (
        0,
        0,
        0,
    )
    async with factory() as session:
        event = await session.scalar(
            select(OutboxEventRow).where(OutboxEventRow.event_id == event_id)
        )
        deliveries = list((await session.scalars(select(NotificationDeliveryRow))).all())
    assert event is not None and event.status == "published" and event.published_at == NOW
    assert len(deliveries) == 1
    assert deliveries[0].tenant_id == NORTHSTAR_TENANT_ID.value
    assert event.correlation_id == deliveries[0].correlation_id == "phase11-correlation"
    assert deliveries[0].payload == {
        "lead_id": deliveries[0].payload["lead_id"],
        "priority": "high",
    }


@pytest.mark.asyncio
async def test_notification_claims_recover_stale_leases_and_record_terminal_state(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyBackgroundStore(factory)
    subscription = NotificationSubscription(
        uuid4(),
        NORTHSTAR_TENANT_ID,
        NotificationChannel.TELEGRAM,
        "222",
        frozenset({"handoff.queued"}),
    )
    await store.save_subscription(subscription)
    event_id = uuid4()
    async with factory() as session, session.begin():
        session.add(
            NotificationDeliveryRow(
                id=uuid4(),
                tenant_id=NORTHSTAR_TENANT_ID.value,
                event_id=event_id,
                subscription_id=subscription.id,
                event_type="handoff.queued",
                channel="telegram",
                recipient_id="222",
                payload={"handoff_id": str(uuid4()), "priority": "urgent"},
                status="processing",
                attempts=1,
                available_at=NOW - timedelta(minutes=2),
                locked_at=NOW - timedelta(minutes=2),
            )
        )
    claims = await store.claim_notifications(now=NOW, limit=10, lease_seconds=60)
    assert len(claims) == 1 and claims[0].attempts == 2
    await store.dead_letter(claims[0], at=NOW, error_code="telegram.forbidden")
    health = await store.health(NORTHSTAR_TENANT_ID)
    assert health.dead_letters == 1 and health.processing_notifications == 0
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(NotificationDeliveryRow)
            .where(NotificationDeliveryRow.last_error_code == "telegram.forbidden")
        )
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_notification_claimers_do_not_share_work(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    store = SQLAlchemyBackgroundStore(factory)
    subscription = await store.save_subscription(
        NotificationSubscription(
            uuid4(),
            NORTHSTAR_TENANT_ID,
            NotificationChannel.TELEGRAM,
            "130013",
            frozenset({"handoff.queued"}),
        )
    )
    async with factory() as session, session.begin():
        session.add(
            NotificationDeliveryRow(
                id=uuid4(),
                tenant_id=NORTHSTAR_TENANT_ID.value,
                event_id=uuid4(),
                subscription_id=subscription.id,
                event_type="handoff.queued",
                channel="telegram",
                recipient_id="130013",
                payload={"priority": "normal"},
                status="pending",
                attempts=0,
                available_at=NOW,
            )
        )
    batches = await asyncio.gather(
        store.claim_notifications(now=NOW, limit=1, lease_seconds=60),
        store.claim_notifications(now=NOW, limit=1, lease_seconds=60),
    )
    assert sum(len(batch) for batch in batches) == 1
