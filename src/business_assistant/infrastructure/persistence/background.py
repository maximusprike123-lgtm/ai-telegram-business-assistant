"""PostgreSQL leases, outbox projection, and notification delivery state."""

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.background import (
    DeliveryClaim,
    NotificationChannel,
    NotificationSubscription,
    WorkerHealth,
)
from business_assistant.domain.shared import TenantId

from .sqlalchemy.models import (
    NotificationDeliveryRow,
    NotificationSubscriptionRow,
    OutboxEventRow,
)


class SQLAlchemyBackgroundStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_subscription(
        self, subscription: NotificationSubscription
    ) -> NotificationSubscription:
        async with self._session_factory() as session, session.begin():
            statement = (
                insert(NotificationSubscriptionRow)
                .values(
                    id=subscription.id,
                    tenant_id=subscription.tenant_id.value,
                    channel=subscription.channel.value,
                    recipient_id=subscription.recipient_id,
                    event_types=sorted(subscription.event_types),
                    enabled=subscription.enabled,
                )
                .on_conflict_do_update(
                    index_elements=("tenant_id", "channel", "recipient_id"),
                    set_={
                        "event_types": sorted(subscription.event_types),
                        "enabled": subscription.enabled,
                        "updated_at": func.now(),
                    },
                )
                .returning(NotificationSubscriptionRow)
            )
            row = (await session.scalars(statement)).one()
            return _subscription(row)

    async def list_subscriptions(self, tenant_id: TenantId) -> tuple[NotificationSubscription, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(NotificationSubscriptionRow)
                    .where(NotificationSubscriptionRow.tenant_id == tenant_id.value)
                    .order_by(NotificationSubscriptionRow.id)
                )
            ).all()
        return tuple(_subscription(row) for row in rows)

    async def dispatch_outbox(
        self, *, now: datetime, limit: int, lease_seconds: int, max_attempts: int
    ) -> tuple[int, int, int]:
        stale_before = now - timedelta(seconds=lease_seconds)
        projected = dead = 0
        async with self._session_factory() as session, session.begin():
            events = list(
                (
                    await session.scalars(
                        select(OutboxEventRow)
                        .where(
                            or_(
                                (OutboxEventRow.status == "pending")
                                & (OutboxEventRow.available_at <= now),
                                (OutboxEventRow.status == "processing")
                                & (OutboxEventRow.locked_at <= stale_before),
                            )
                        )
                        .order_by(OutboxEventRow.available_at, OutboxEventRow.id)
                        .with_for_update(skip_locked=True)
                        .limit(limit)
                    )
                ).all()
            )
            for event in events:
                event.status = "processing"
                event.locked_at = now
                event.attempts += 1
                if event.attempts > max_attempts:
                    event.status = "dead_letter"
                    event.last_error_code = "outbox.attempts_exhausted"
                    dead += 1
                    continue
                subscriptions = (
                    await session.scalars(
                        select(NotificationSubscriptionRow).where(
                            NotificationSubscriptionRow.tenant_id == event.tenant_id,
                            NotificationSubscriptionRow.enabled.is_(True),
                            NotificationSubscriptionRow.event_types.contains([event.event_type]),
                        )
                    )
                ).all()
                for subscription in subscriptions:
                    statement = (
                        insert(NotificationDeliveryRow)
                        .values(
                            id=uuid4(),
                            tenant_id=event.tenant_id,
                            event_id=event.event_id,
                            correlation_id=event.correlation_id,
                            subscription_id=subscription.id,
                            event_type=event.event_type,
                            channel=subscription.channel,
                            recipient_id=subscription.recipient_id,
                            payload=event.payload,
                            status="pending",
                            attempts=0,
                            available_at=now,
                        )
                        .on_conflict_do_nothing(
                            index_elements=("tenant_id", "event_id", "subscription_id")
                        )
                    )
                    result = await session.execute(statement)
                    projected += int(cast(CursorResult[Any], result).rowcount or 0)
                event.status = "published"
                event.published_at = now
                event.locked_at = None
                event.last_error_code = None
        return len(events), projected, dead

    async def claim_notifications(
        self, *, now: datetime, limit: int, lease_seconds: int
    ) -> tuple[DeliveryClaim, ...]:
        stale_before = now - timedelta(seconds=lease_seconds)
        async with self._session_factory() as session, session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(NotificationDeliveryRow)
                        .where(
                            or_(
                                (NotificationDeliveryRow.status == "pending")
                                & (NotificationDeliveryRow.available_at <= now),
                                (NotificationDeliveryRow.status == "processing")
                                & (NotificationDeliveryRow.locked_at <= stale_before),
                            )
                        )
                        .order_by(
                            NotificationDeliveryRow.available_at,
                            NotificationDeliveryRow.id,
                        )
                        .with_for_update(skip_locked=True)
                        .limit(limit)
                    )
                ).all()
            )
            claims: list[DeliveryClaim] = []
            for row in rows:
                row.status = "processing"
                row.locked_at = now
                row.attempts += 1
                claims.append(_claim(row))
            return tuple(claims)

    async def mark_delivered(self, claim: DeliveryClaim, *, at: datetime) -> None:
        await self._finish(claim, status="sent", at=at, error_code=None)

    async def retry_delivery(self, claim: DeliveryClaim, *, at: datetime, error_code: str) -> None:
        await self._finish(claim, status="pending", at=at, error_code=error_code)

    async def dead_letter(self, claim: DeliveryClaim, *, at: datetime, error_code: str) -> None:
        await self._finish(claim, status="dead_letter", at=at, error_code=error_code)

    async def _finish(
        self,
        claim: DeliveryClaim,
        *,
        status: str,
        at: datetime,
        error_code: str | None,
    ) -> None:
        values: dict[str, object] = {
            "status": status,
            "locked_at": None,
            "last_error_code": error_code,
        }
        if status == "pending":
            values["available_at"] = at
        elif status == "sent":
            values["sent_at"] = at
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(NotificationDeliveryRow)
                .where(
                    NotificationDeliveryRow.tenant_id == claim.tenant_id.value,
                    NotificationDeliveryRow.id == claim.id,
                    NotificationDeliveryRow.status == "processing",
                )
                .values(**values)
            )

    async def health(self, tenant_id: TenantId) -> WorkerHealth:
        async with self._session_factory() as session:
            outbox = await session.scalar(
                select(func.count())
                .select_from(OutboxEventRow)
                .where(
                    OutboxEventRow.tenant_id == tenant_id.value,
                    OutboxEventRow.status == "pending",
                )
            )
            counts: dict[str, int] = {
                status: int(count)
                for status, count in (
                    await session.execute(
                        select(NotificationDeliveryRow.status, func.count())
                        .where(NotificationDeliveryRow.tenant_id == tenant_id.value)
                        .group_by(NotificationDeliveryRow.status)
                    )
                ).all()
            }
            oldest = await session.scalar(
                select(func.min(NotificationDeliveryRow.available_at)).where(
                    NotificationDeliveryRow.tenant_id == tenant_id.value,
                    NotificationDeliveryRow.status == "pending",
                )
            )
            last_success = await session.scalar(
                select(func.max(NotificationDeliveryRow.sent_at)).where(
                    NotificationDeliveryRow.tenant_id == tenant_id.value,
                    NotificationDeliveryRow.status == "sent",
                )
            )
        return WorkerHealth(
            int(outbox or 0),
            int(counts.get("pending", 0)),
            int(counts.get("processing", 0)),
            int(counts.get("dead_letter", 0)),
            oldest,
            last_success,
        )


def _subscription(row: NotificationSubscriptionRow) -> NotificationSubscription:
    return NotificationSubscription(
        row.id,
        TenantId(row.tenant_id),
        NotificationChannel(row.channel),
        row.recipient_id,
        frozenset(row.event_types),
        row.enabled,
    )


def _claim(row: NotificationDeliveryRow) -> DeliveryClaim:
    return DeliveryClaim(
        row.id,
        TenantId(row.tenant_id),
        row.event_type,
        NotificationChannel(row.channel),
        row.recipient_id,
        dict(row.payload),
        row.attempts,
        row.correlation_id,
    )
