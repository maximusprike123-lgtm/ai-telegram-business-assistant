from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_TENANT_ID,
    northstar_services,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    BookingRow,
    BusinessScheduleRow,
    CustomerRow,
    ResourceRow,
    ServiceCategoryRow,
    ServiceResourceRow,
    ServiceRow,
    TenantRow,
)

pytestmark = pytest.mark.postgresql


def tenant_row(tenant_id: UUID, slug: str) -> TenantRow:
    return TenantRow(
        id=tenant_id,
        slug=slug,
        name=slug,
        timezone="Europe/Moscow",
        default_locale="en",
        supported_locales=["en"],
        status="active",
        settings_version=1,
    )


@pytest.mark.asyncio
async def test_composite_fk_rejects_cross_tenant_catalog_relationship(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    first, second, category_id = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add_all([tenant_row(first, "catalog-one"), tenant_row(second, "catalog-two")])
        await session.flush()
        session.add(
            ServiceCategoryRow(id=category_id, tenant_id=first, names={"en": "Care"}, sort_order=0)
        )
        await session.flush()
        session.add(
            ServiceRow(
                id=uuid4(),
                tenant_id=second,
                category_id=category_id,
                code="invalid",
                names={"en": "Invalid"},
                descriptions={"en": "Invalid"},
                duration_seconds=60,
                buffer_seconds=0,
                price_mode="quote_required",
                preparation_notes={},
                eligibility_notes={},
                active=True,
                bookable=True,
                version=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_database_rejects_overlapping_active_bookings_for_one_resource(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    tenant_id, customer_id, category_id = uuid4(), uuid4(), uuid4()
    service_id, schedule_id, resource_id = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add(tenant_row(tenant_id, "booking-shop"))
        await session.flush()
        session.add_all(
            [
                CustomerRow(
                    id=customer_id,
                    tenant_id=tenant_id,
                    locale="en",
                    status="active",
                    phone_verified=False,
                ),
                ServiceCategoryRow(
                    id=category_id, tenant_id=tenant_id, names={"en": "Care"}, sort_order=0
                ),
                BusinessScheduleRow(
                    id=schedule_id,
                    tenant_id=tenant_id,
                    name="Hours",
                    timezone="Europe/Moscow",
                    active=True,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ServiceRow(
                    id=service_id,
                    tenant_id=tenant_id,
                    category_id=category_id,
                    code="inspection",
                    names={"en": "Inspection"},
                    descriptions={"en": "Inspection"},
                    duration_seconds=3600,
                    buffer_seconds=0,
                    price_mode="quote_required",
                    preparation_notes={},
                    eligibility_notes={},
                    active=True,
                    bookable=True,
                    version=1,
                ),
                ResourceRow(
                    id=resource_id,
                    tenant_id=tenant_id,
                    schedule_id=schedule_id,
                    resource_type="bay",
                    capacity=1,
                    active=True,
                ),
            ]
        )
        await session.flush()
        starts_at = datetime(2026, 8, 3, 7, tzinfo=UTC)
        common = {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "service_id": service_id,
            "resource_id": resource_id,
            "status": "confirmed",
            "service_snapshot": {"code": "inspection"},
            "customer_snapshot": {"id": "safe"},
        }
        session.add(
            BookingRow(
                id=uuid4(),
                start_at=starts_at,
                end_at=starts_at + timedelta(hours=1),
                idempotency_scope="test",
                idempotency_value="one",
                **common,
            )
        )
        await session.flush()
        session.add(
            BookingRow(
                id=uuid4(),
                start_at=starts_at + timedelta(minutes=30),
                end_at=starts_at + timedelta(hours=2),
                idempotency_scope="test",
                idempotency_value="two",
                **common,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_phase5_assignment_rejects_cross_tenant_service_and_resource(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    other_tenant, schedule_id, resource_id = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add(tenant_row(other_tenant, "other-booking-shop"))
        await session.flush()
        session.add(
            BusinessScheduleRow(
                id=schedule_id,
                tenant_id=other_tenant,
                name="Hours",
                timezone="Europe/Moscow",
                active=True,
            )
        )
        await session.flush()
        session.add(
            ResourceRow(
                id=resource_id,
                tenant_id=other_tenant,
                schedule_id=schedule_id,
                resource_type="bay",
                capacity=1,
                active=True,
            )
        )
        await session.flush()
        session.add(
            ServiceResourceRow(
                id=uuid4(),
                tenant_id=other_tenant,
                service_id=northstar_services()[0].id.value,
                resource_id=resource_id,
                required_capacity=1,
                active=True,
            )
        )
        assert other_tenant != NORTHSTAR_TENANT_ID.value
        with pytest.raises(IntegrityError):
            await session.flush()
