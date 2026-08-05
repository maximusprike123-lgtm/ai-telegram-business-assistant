"""Celery worker and beat composition for Phase 10 background operations."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

import httpx
from aiogram import Bot
from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.background import (
    BackgroundApplication,
    DeliveryClaim,
    RetryPolicy,
)
from business_assistant.application.observability import (
    Component,
    Operation,
    Outcome,
    correlation_scope,
    current_correlation_id,
)
from business_assistant.config import RuntimeSettings, load_settings
from business_assistant.infrastructure.notifications import TelegramNotificationGateway
from business_assistant.infrastructure.observability import (
    PrometheusMetrics,
)
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBackgroundStore,
    SQLAlchemyBookingStore,
    SQLAlchemyPrivacyStore,
    create_engine,
    create_session_factory,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import WorkerRunRow
from business_assistant.infrastructure.system import UTCClock

OUTBOX_TASK = "business_assistant.background.dispatch_outbox"
DELIVERY_TASK = "business_assistant.background.deliver_notifications"
HOLD_TASK = "business_assistant.background.expire_holds"
RETENTION_TASK = "business_assistant.background.execute_retention"
REINDEX_TASK = "business_assistant.background.reindex_knowledge"
_WORKER_METRICS = PrometheusMetrics()


class _UnusedGateway:
    async def send(self, claim: DeliveryClaim, *, text: str) -> None:
        raise RuntimeError("Notification gateway is unavailable")


def create_worker_app(settings: RuntimeSettings | None = None) -> Celery:
    runtime = settings or load_settings()
    app = Celery(
        "business_assistant",
        broker=runtime.celery.broker_url or "memory://",
        backend=runtime.celery.result_backend_url if runtime.celery.results_enabled else None,
    )
    app.conf.update(
        task_ignore_result=not runtime.celery.results_enabled,
        task_serializer="json",
        accept_content=("json",),
        result_serializer="json",
        enable_utc=True,
        timezone="UTC",
        task_routes={
            OUTBOX_TASK: {"queue": "default"},
            DELIVERY_TASK: {"queue": "notifications"},
            HOLD_TASK: {"queue": "maintenance"},
            RETENTION_TASK: {"queue": "maintenance"},
            REINDEX_TASK: {"queue": "knowledge"},
        },
        beat_schedule={
            "dispatch-outbox": {"task": OUTBOX_TASK, "schedule": 5.0},
            "deliver-notifications": {"task": DELIVERY_TASK, "schedule": 5.0},
            "expire-holds": {"task": HOLD_TASK, "schedule": 60.0},
            "execute-retention": {"task": RETENTION_TASK, "schedule": 86400.0},
            "reindex-knowledge": {"task": REINDEX_TASK, "schedule": 3600.0},
        },
        broker_connection_retry_on_startup=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=runtime.celery.task_soft_time_limit_seconds,
        task_time_limit=runtime.celery.task_time_limit_seconds,
        broker_connection_max_retries=10,
    )

    @app.task(name=OUTBOX_TASK)  # type: ignore[untyped-decorator]
    def dispatch_outbox() -> int:
        return asyncio.run(_execute(runtime, OUTBOX_TASK, _dispatch_outbox))

    @app.task(name=DELIVERY_TASK)  # type: ignore[untyped-decorator]
    def deliver_notifications() -> int:
        if not runtime.celery.notification_delivery_enabled:
            return 0
        return asyncio.run(_execute(runtime, DELIVERY_TASK, _deliver_notifications))

    @app.task(name=HOLD_TASK)  # type: ignore[untyped-decorator]
    def expire_holds() -> int:
        return asyncio.run(_execute(runtime, HOLD_TASK, _expire_holds))

    @app.task(name=RETENTION_TASK)  # type: ignore[untyped-decorator]
    def execute_retention() -> int:
        return asyncio.run(_execute(runtime, RETENTION_TASK, _execute_retention))

    @app.task(name=REINDEX_TASK)  # type: ignore[untyped-decorator]
    def reindex_knowledge() -> int:
        if not runtime.features.rag_enabled:
            return 0
        return asyncio.run(_execute(runtime, REINDEX_TASK, _reindex_knowledge))

    return app


async def _execute(
    settings: RuntimeSettings,
    task_name: str,
    operation: Callable[[RuntimeSettings, async_sessionmaker[AsyncSession]], Awaitable[int]],
) -> int:
    engine = create_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        connect_timeout_seconds=settings.database.connect_timeout_seconds,
    )
    factory = create_session_factory(engine)
    started = datetime.now(UTC)
    timer = monotonic()
    with correlation_scope(None):
        try:
            processed = await operation(settings, factory)
        except Exception:
            await _record(factory, task_name, "failed", 0, "worker.unexpected", started)
            _WORKER_METRICS.observe(
                Component.CELERY, Operation.TASK, Outcome.FAILURE, monotonic() - timer
            )
            raise
        else:
            await _record(factory, task_name, "success", processed, None, started)
            _WORKER_METRICS.observe(
                Component.CELERY, Operation.TASK, Outcome.SUCCESS, monotonic() - timer
            )
            return processed
        finally:
            await engine.dispose()


def _background(
    settings: RuntimeSettings,
    factory: async_sessionmaker[AsyncSession],
    gateway: TelegramNotificationGateway | _UnusedGateway,
) -> BackgroundApplication:
    return BackgroundApplication(
        SQLAlchemyBackgroundStore(factory),
        gateway,
        UTCClock(),
        RetryPolicy(
            settings.celery.max_attempts,
            settings.celery.retry_base_seconds,
            settings.celery.retry_max_seconds,
        ),
        _WORKER_METRICS,
    )


async def _dispatch_outbox(
    settings: RuntimeSettings, factory: async_sessionmaker[AsyncSession]
) -> int:
    claimed, _projected, _dead = await _background(
        settings, factory, _UnusedGateway()
    ).dispatch_outbox(
        limit=settings.celery.batch_size,
        lease_seconds=settings.celery.lease_seconds,
    )
    return claimed


async def _deliver_notifications(
    settings: RuntimeSettings, factory: async_sessionmaker[AsyncSession]
) -> int:
    if settings.telegram.bot_token is None:
        raise RuntimeError("Enabled notification delivery requires a Telegram token")
    bot = Bot(settings.telegram.bot_token)
    try:
        outcome = await _background(
            settings, factory, TelegramNotificationGateway(bot)
        ).deliver_notifications(
            limit=settings.celery.batch_size,
            lease_seconds=settings.celery.lease_seconds,
        )
        return outcome.claimed
    finally:
        await bot.session.close()


async def _expire_holds(
    settings: RuntimeSettings, factory: async_sessionmaker[AsyncSession]
) -> int:
    return await SQLAlchemyBookingStore(factory).expire_holds(
        now=UTCClock().now(), limit=settings.celery.batch_size
    )


async def _execute_retention(
    settings: RuntimeSettings, factory: async_sessionmaker[AsyncSession]
) -> int:
    return await SQLAlchemyPrivacyStore(factory).run_scheduled_retention(
        at=UTCClock().now(), limit=settings.celery.batch_size
    )


async def _reindex_knowledge(
    settings: RuntimeSettings, factory: async_sessionmaker[AsyncSession]
) -> int:
    from business_assistant.bootstrap.knowledge import build_knowledge_application

    async with httpx.AsyncClient() as client:
        application = build_knowledge_application(settings, factory, client, _WORKER_METRICS)
        if application is None:
            return 0
        return await application.reindex(limit=settings.celery.batch_size)


async def _record(
    factory: async_sessionmaker[AsyncSession],
    task_name: str,
    status: str,
    processed: int,
    error_code: str | None,
    started: datetime,
) -> None:
    async with factory() as session, session.begin():
        session.add(
            WorkerRunRow(
                id=uuid4(),
                correlation_id=current_correlation_id(),
                tenant_id=None,
                task_name=task_name,
                status=status,
                processed_count=processed,
                error_code=error_code,
                started_at=started,
                finished_at=datetime.now(UTC),
            )
        )


def main() -> None:
    settings = load_settings()
    if not settings.celery.enabled:
        raise SystemExit("CELERY_ENABLED must be true")
    create_worker_app(settings).worker_main(
        ["worker", "--loglevel=INFO", "-Q", "default,notifications,maintenance,knowledge"]
    )


def beat_main() -> None:
    settings = load_settings()
    if not settings.celery.enabled:
        raise SystemExit("CELERY_ENABLED must be true")
    create_worker_app(settings).Beat().run()
