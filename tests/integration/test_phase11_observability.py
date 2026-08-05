import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.observability import DependencyStatus
from business_assistant.config import load_settings
from business_assistant.infrastructure.observability import (
    DependencyHealthChecker,
    PrometheusMetrics,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_readiness_verifies_postgresql_pgvector_and_ignores_disabled_features(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    settings = load_settings(
        {
            "APP_ENV": "test",
            "PUBLIC_BASE_URL": "http://localhost:8000",
            "DATABASE_URL": postgresql_url,
            "INTERNAL_API_ENABLED": "false",
        }
    )
    report = await DependencyHealthChecker(settings, factory, PrometheusMetrics()).check()
    states = {item.name: item.status for item in report.dependencies}
    assert report.ready
    assert states["postgresql"] is DependencyStatus.HEALTHY
    assert states["pgvector"] is DependencyStatus.HEALTHY
    assert states["redis"] is DependencyStatus.DISABLED
    assert states["telegram"] is DependencyStatus.DISABLED
    assert states["ai_provider"] is DependencyStatus.DISABLED
