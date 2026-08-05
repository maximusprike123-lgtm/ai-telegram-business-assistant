"""Safe dependency diagnostics with feature-aware readiness policy."""

import asyncio
from datetime import UTC, datetime
from time import monotonic

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.observability import (
    Component,
    DependencyCheck,
    DependencyStatus,
    DiagnosticReport,
    Operation,
    OperationalMetricsPort,
    Outcome,
)
from business_assistant.config import RuntimeSettings


class DependencyHealthChecker:
    def __init__(
        self,
        settings: RuntimeSettings,
        session_factory: async_sessionmaker[AsyncSession],
        metrics: OperationalMetricsPort,
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._metrics = metrics
        self._timeout = timeout_seconds

    async def check(self) -> DiagnosticReport:
        database, vector = await self._database_checks()
        checks = (
            database,
            vector,
            await self._redis_check(),
            self._telegram_check(),
            self._ai_check(),
        )
        ready = all(
            not item.required
            or item.status in {DependencyStatus.HEALTHY, DependencyStatus.DISABLED}
            for item in checks
        )
        return DiagnosticReport(ready, datetime.now(UTC), checks)

    async def _database_checks(self) -> tuple[DependencyCheck, DependencyCheck]:
        started = monotonic()
        try:
            async with asyncio.timeout(self._timeout), self._session_factory() as session:
                await session.execute(text("SELECT 1"))
                vector = await session.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                )
        except Exception:
            latency = _milliseconds(started)
            self._observe(Outcome.FAILURE, started)
            unavailable = DependencyCheck(
                "postgresql",
                DependencyStatus.UNAVAILABLE,
                True,
                latency,
                "dependency.database_unavailable",
            )
            return unavailable, DependencyCheck(
                "pgvector",
                DependencyStatus.UNAVAILABLE,
                True,
                latency,
                "dependency.database_unavailable",
            )
        latency = _milliseconds(started)
        self._observe(Outcome.SUCCESS if vector else Outcome.FAILURE, started)
        return (
            DependencyCheck("postgresql", DependencyStatus.HEALTHY, True, latency),
            DependencyCheck(
                "pgvector",
                DependencyStatus.HEALTHY if vector else DependencyStatus.UNAVAILABLE,
                True,
                latency,
                None if vector else "dependency.pgvector_missing",
            ),
        )

    async def _redis_check(self) -> DependencyCheck:
        required = self._settings.redis.enabled
        url = self._settings.redis.url
        if not required or url is None:
            return DependencyCheck("redis", DependencyStatus.DISABLED, False, 0)
        started = monotonic()
        client = Redis.from_url(
            url,
            socket_timeout=self._timeout,
            socket_connect_timeout=self._timeout,
        )
        try:
            async with asyncio.timeout(self._timeout):
                healthy = bool(await client.ping())
        except Exception:
            healthy = False
        finally:
            await client.aclose()
        return DependencyCheck(
            "redis",
            DependencyStatus.HEALTHY if healthy else DependencyStatus.UNAVAILABLE,
            True,
            _milliseconds(started),
            None if healthy else "dependency.redis_unavailable",
        )

    def _telegram_check(self) -> DependencyCheck:
        config = self._settings.telegram
        if not config.enabled:
            return DependencyCheck("telegram", DependencyStatus.DISABLED, False, 0)
        healthy = (
            config.bot_token is not None
            and config.bot_id is not None
            and config.tenant_id is not None
        )
        return DependencyCheck(
            "telegram",
            DependencyStatus.HEALTHY if healthy else DependencyStatus.UNAVAILABLE,
            True,
            0,
            None if healthy else "dependency.telegram_config_invalid",
        )

    def _ai_check(self) -> DependencyCheck:
        if not self._settings.ai.enabled:
            return DependencyCheck("ai_provider", DependencyStatus.DISABLED, False, 0)
        healthy = (
            self._settings.openai.enabled
            and self._settings.openai.api_key is not None
            and self._settings.ai.router_model is not None
            and self._settings.ai.response_model is not None
        )
        return DependencyCheck(
            "ai_provider",
            DependencyStatus.HEALTHY if healthy else DependencyStatus.UNAVAILABLE,
            True,
            0,
            None if healthy else "dependency.ai_config_invalid",
        )

    def _observe(self, outcome: Outcome, started: float) -> None:
        self._metrics.observe(
            Component.DATABASE,
            Operation.HEALTH_CHECK,
            outcome,
            monotonic() - started,
        )


def _milliseconds(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
