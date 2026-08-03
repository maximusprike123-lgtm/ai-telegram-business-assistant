from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import DuplicateEntityError
from business_assistant.domain.customers import Customer
from business_assistant.domain.shared import CustomerId, Locale, TenantId
from business_assistant.domain.tenants import Tenant
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)

pytestmark = pytest.mark.postgresql


def tenant(tenant_id: TenantId, slug: str) -> Tenant:
    return Tenant(tenant_id, slug, slug.title(), "Europe/Moscow", Locale.EN, frozenset({Locale.EN}))


@pytest.mark.asyncio
async def test_repository_round_trip_and_cross_tenant_read_isolation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    first = TenantId.new()
    second = TenantId.new()
    customer = Customer(CustomerId.new(), first, Locale.EN, display_name="Ada")
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.tenants.add(first, tenant(first, "first-shop"))
        await uow.tenants.add(second, tenant(second, "second-shop"))
        await uow.customers.add(first, customer)
        await uow.commit()

    async with SQLAlchemyUnitOfWork(factory) as uow:
        loaded = await uow.customers.get(first, customer.id)
        leaked = await uow.customers.get(second, customer.id)
        page = await uow.customers.list_page(first, cursor=None, limit=20)
    assert loaded == customer
    assert leaked is None
    assert page == [customer]


@pytest.mark.asyncio
async def test_uncommitted_uow_rolls_back_and_duplicate_is_translated(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    tenant_id = TenantId.new()
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.tenants.add(tenant_id, tenant(tenant_id, "rollback-shop"))
    async with SQLAlchemyUnitOfWork(factory) as uow:
        assert await uow.tenants.get(tenant_id, tenant_id) is None
        await uow.tenants.add(tenant_id, tenant(tenant_id, "duplicate-shop"))
        await uow.commit()
    with pytest.raises(DuplicateEntityError):
        async with SQLAlchemyUnitOfWork(factory) as uow:
            await uow.tenants.add(tenant_id, tenant(tenant_id, "duplicate-shop"))


@pytest.mark.asyncio
async def test_utc_timestamps_round_trip_without_timezone_loss(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    tenant_id = TenantId.new()
    accepted = datetime(2026, 8, 2, 10, tzinfo=UTC)
    customer = Customer(
        CustomerId.new(),
        tenant_id,
        Locale.EN,
        privacy_notice_version="demo-v1",
        privacy_accepted_at=accepted,
        contact_consent_at=accepted + timedelta(minutes=1),
    )
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.tenants.add(tenant_id, tenant(tenant_id, "utc-shop"))
        await uow.customers.add(tenant_id, customer)
        await uow.commit()
    async with SQLAlchemyUnitOfWork(factory) as uow:
        loaded = await uow.customers.get(tenant_id, customer.id)
    assert loaded is not None
    assert loaded.privacy_accepted_at == accepted
    assert loaded.privacy_accepted_at.utcoffset() == timedelta(0)
