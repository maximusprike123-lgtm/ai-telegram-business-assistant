import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.domain.shared import Locale
from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_CATEGORY_ID,
    NORTHSTAR_TENANT_ID,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    ScheduleOverrideRow,
    ServiceRow,
    TenantPublicProfileRow,
)
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_northstar_seed_is_complete_and_idempotent(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    await seed_northstar(postgresql_url, "test")
    async with SQLAlchemyUnitOfWork(factory) as uow:
        tenant = await uow.tenants.get(NORTHSTAR_TENANT_ID, NORTHSTAR_TENANT_ID)
        category = await uow.categories.get(NORTHSTAR_TENANT_ID, NORTHSTAR_CATEGORY_ID)
        profile = await uow.public_profiles.get(NORTHSTAR_TENANT_ID)
        services = await uow.services.list_page(NORTHSTAR_TENANT_ID, cursor=None, limit=20)
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ServiceRow)
            .where(ServiceRow.tenant_id == NORTHSTAR_TENANT_ID.value)
        )
        profile_count = await session.scalar(
            select(func.count()).select_from(TenantPublicProfileRow)
        )
        override_count = await session.scalar(select(func.count()).select_from(ScheduleOverrideRow))
    assert tenant is not None
    assert category is not None
    assert profile is not None
    assert "fictional demo" in tenant.name
    assert tenant.default_locale is Locale.EN
    assert tenant.supported_locales == frozenset({Locale.EN})
    assert set(category.names) == {Locale.EN}
    assert set(profile.descriptions) == {Locale.EN}
    assert all(set(service.names) == {Locale.EN} for service in services)
    assert all(set(service.descriptions) == {Locale.EN} for service in services)
    assert {service.code for service in services} == {
        "oil-change",
        "brake-inspection",
        "engine-diagnostics",
        "tire-service",
        "battery-replacement",
        "suspension-inspection",
    }
    assert count == 6
    assert profile_count == 1
    assert override_count == 2
    assert {service.price.mode.value for service in services} == {
        "exact",
        "starting_from",
        "quote_required",
    }


@pytest.mark.asyncio
async def test_seed_refuses_production(postgresql_url: str) -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        await seed_northstar(postgresql_url, "production")
