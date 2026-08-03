from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.helpers_phase3 import FixedClock

from business_assistant.application.catalog import ListServices
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.infrastructure.persistence.seed import NORTHSTAR_TENANT_ID, seed_northstar
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_phase3_profile_and_catalog_queries_are_tenant_scoped_on_postgresql(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")

    def uow_factory() -> Phase3UnitOfWork:
        return cast(Phase3UnitOfWork, SQLAlchemyUnitOfWork(factory))

    typed_factory: Phase3UnitOfWorkFactory = uow_factory
    principal = Principal("integration", NORTHSTAR_TENANT_ID, Role.VIEWER)
    services = await ListServices(typed_factory).execute(principal, "ru")
    profile_result = await GetTenantPublicProfile(
        typed_factory, FixedClock(datetime(2026, 8, 3, 6, 30, tzinfo=UTC))
    ).execute(principal, "en")
    assert len(services) == 6
    assert all(item.locale == "ru" for item in services)
    assert "fictional demo" in profile_result.name
    assert profile_result.status.open_now
    async with SQLAlchemyUnitOfWork(factory) as uow:
        profile = await uow.public_profiles.get(NORTHSTAR_TENANT_ID)
        assert profile is not None
        assert await uow.public_profiles.get(NORTHSTAR_TENANT_ID.new()) is None


def test_fixed_clock_used_by_phase3_test_fixture() -> None:
    clock = FixedClock(datetime(2026, 8, 3, tzinfo=UTC))
    assert clock.now().tzinfo is UTC
