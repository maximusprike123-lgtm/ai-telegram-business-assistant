import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_TENANT_ID,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import ServiceRow
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
        services = await uow.services.list_page(NORTHSTAR_TENANT_ID, cursor=None, limit=20)
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ServiceRow)
            .where(ServiceRow.tenant_id == NORTHSTAR_TENANT_ID.value)
        )
    assert tenant is not None
    assert "fictional demo" in tenant.name
    assert {service.code for service in services} == {
        "oil-change",
        "brake-inspection",
        "engine-diagnostics",
        "tire-service",
        "battery-replacement",
        "suspension-inspection",
    }
    assert count == 6


@pytest.mark.asyncio
async def test_seed_refuses_production(postgresql_url: str) -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        await seed_northstar(postgresql_url, "production")
