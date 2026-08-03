"""Idempotent, non-production seed for the fictional Northstar demo tenant."""

import asyncio
import os
from datetime import date, time, timedelta
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from business_assistant.domain.catalog import Service, ServiceCategory
from business_assistant.domain.scheduling import (
    BusinessSchedule,
    ScheduleInterval,
    ScheduleOverride,
)
from business_assistant.domain.shared import (
    CategoryId,
    Locale,
    Money,
    PriceMode,
    PricePresentation,
    ScheduleId,
    ServiceId,
    TenantId,
)
from business_assistant.domain.tenants import Tenant, TenantPublicProfile

from .sqlalchemy.engine import create_engine, create_session_factory
from .sqlalchemy.models import BookingPolicyRow, ResourceRow, ServiceResourceRow
from .sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork

NORTHSTAR_TENANT_ID = TenantId(UUID("f73f5ad0-05c8-5bc6-a2c7-166b959fa73e"))
NORTHSTAR_CATEGORY_ID = CategoryId(UUID("43ec952c-c4f4-5387-9cb9-cbe42dd16ef5"))
NORTHSTAR_SCHEDULE_ID = ScheduleId(UUID("9419ac4d-a535-5f3b-99f0-f51f6a6e042a"))
NORTHSTAR_RESOURCE_IDS = (
    UUID("ad08e178-17a7-5512-8734-cb6aff4018d0"),
    UUID("d1e30ca4-b9ba-59ca-8ae4-1962c6dc6eee"),
)

_SERVICE_IDS = {
    "oil-change": ServiceId(UUID("ec416e09-15a1-54a4-9553-01d97b1b83e4")),
    "brake-inspection": ServiceId(UUID("056faeb8-a8aa-52f8-8071-1fa2fd8aa60c")),
    "engine-diagnostics": ServiceId(UUID("b2bdbfa5-57ab-5957-8e31-d3f0828a4f76")),
    "tire-service": ServiceId(UUID("4f08309c-fe77-5d89-ab05-fce2d454f3cd")),
    "battery-replacement": ServiceId(UUID("1030e2e0-6350-5201-a51f-a77c83d406d7")),
    "suspension-inspection": ServiceId(UUID("fc6cabdb-f03a-512b-b218-3ed555c9174e")),
}


def _service(
    code: str,
    english_name: str,
    duration_minutes: int,
    price_mode: PriceMode,
    starting_price_minor: int | None,
) -> Service:
    price = PricePresentation(
        price_mode,
        Money(starting_price_minor, "RUB") if starting_price_minor is not None else None,
    )
    return Service(
        id=_SERVICE_IDS[code],
        tenant_id=NORTHSTAR_TENANT_ID,
        category_id=NORTHSTAR_CATEGORY_ID,
        code=code,
        names={Locale.EN: english_name},
        descriptions={
            Locale.EN: f"{english_name} appointment at the fictional Northstar workshop."
        },
        duration=timedelta(minutes=duration_minutes),
        cleanup_buffer=timedelta(minutes=10),
        price=price,
        preparation_notes={
            Locale.EN: "Bring the vehicle registration and describe observed symptoms."
        },
    )


def northstar_services() -> tuple[Service, ...]:
    # Demo-only durations/prices are synthetic defaults, not real offers or universal policy.
    return (
        _service("oil-change", "Oil change", 45, PriceMode.EXACT, 450_000),
        _service(
            "brake-inspection",
            "Brake inspection",
            60,
            PriceMode.STARTING_FROM,
            300_000,
        ),
        _service(
            "engine-diagnostics",
            "Engine diagnostics",
            90,
            PriceMode.STARTING_FROM,
            500_000,
        ),
        _service("tire-service", "Tire service", 60, PriceMode.EXACT, 400_000),
        _service(
            "battery-replacement",
            "Battery replacement",
            45,
            PriceMode.QUOTE_REQUIRED,
            None,
        ),
        _service(
            "suspension-inspection",
            "Suspension inspection",
            60,
            PriceMode.STARTING_FROM,
            350_000,
        ),
    )


async def seed_northstar(database_url: str, app_env: str) -> None:
    if app_env not in {"local", "development", "test"}:
        raise RuntimeError("Northstar demo seed is disabled outside local/development/test")
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    try:
        async with SQLAlchemyUnitOfWork(factory) as uow:
            await uow.tenants.upsert(
                NORTHSTAR_TENANT_ID,
                Tenant(
                    NORTHSTAR_TENANT_ID,
                    "northstar-auto-care",
                    "Northstar Auto Care (fictional demo)",
                    "Europe/Moscow",
                    Locale.EN,
                    frozenset({Locale.EN}),
                ),
            )
            await uow.categories.upsert(
                NORTHSTAR_TENANT_ID,
                ServiceCategory(
                    NORTHSTAR_CATEGORY_ID,
                    NORTHSTAR_TENANT_ID,
                    {Locale.EN: "Auto care"},
                ),
            )
            intervals = (
                *(ScheduleInterval(day, time(8), time(12)) for day in range(5)),
                *(ScheduleInterval(day, time(13), time(18)) for day in range(5)),
                ScheduleInterval(5, time(9), time(15)),
            )
            overrides = (
                ScheduleOverride(date(2027, 1, 1), date(2027, 1, 1), True, reason="Demo holiday"),
                ScheduleOverride(
                    date(2027, 1, 3),
                    date(2027, 1, 3),
                    False,
                    (ScheduleInterval(6, time(10), time(14)),),
                    "Demo special opening",
                ),
            )
            await uow.schedules.replace(
                NORTHSTAR_TENANT_ID,
                BusinessSchedule(
                    NORTHSTAR_SCHEDULE_ID,
                    NORTHSTAR_TENANT_ID,
                    "Workshop hours",
                    "Europe/Moscow",
                    intervals,
                    overrides,
                ),
            )
            await uow.public_profiles.upsert(
                NORTHSTAR_TENANT_ID,
                TenantPublicProfile(
                    tenant_id=NORTHSTAR_TENANT_ID,
                    schedule_id=NORTHSTAR_SCHEDULE_ID,
                    descriptions={
                        Locale.EN: "Fictional auto-care workshop for the portfolio demonstration."
                    },
                    public_phone="+1 555 010 0200",
                    public_email="hello@northstar.example",
                    website_url="https://northstar.example",
                    addresses={Locale.EN: "18 Harbor Road"},
                    parking_guidance={
                        Locale.EN: "Customer parking is beside the workshop entrance."
                    },
                    payment_methods=("cash", "card"),
                    warranty_policy={
                        Locale.EN: "Warranty terms depend on the approved service and parts."
                    },
                    appointment_policy={Locale.EN: "Appointments require workshop confirmation."},
                ),
            )
            for service in northstar_services():
                await uow.services.upsert(NORTHSTAR_TENANT_ID, service)
            await uow.commit()
        async with factory() as session, session.begin():
            await session.execute(
                insert(BookingPolicyRow)
                .values(
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    slot_interval_minutes=30,
                    booking_horizon_days=30,
                    minimum_notice_minutes=120,
                    hold_duration_minutes=5,
                    draft_expiry_minutes=30,
                    change_cutoff_minutes=1440,
                    customer_name_max_length=100,
                    customer_phone_max_length=32,
                    customer_note_max_length=500,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id"],
                    set_={
                        "slot_interval_minutes": 30,
                        "booking_horizon_days": 30,
                        "minimum_notice_minutes": 120,
                        "hold_duration_minutes": 5,
                        "draft_expiry_minutes": 30,
                        "change_cutoff_minutes": 1440,
                        "customer_name_max_length": 100,
                        "customer_phone_max_length": 32,
                        "customer_note_max_length": 500,
                    },
                )
            )
            for resource_id in NORTHSTAR_RESOURCE_IDS:
                await session.execute(
                    insert(ResourceRow)
                    .values(
                        id=resource_id,
                        tenant_id=NORTHSTAR_TENANT_ID.value,
                        schedule_id=NORTHSTAR_SCHEDULE_ID.value,
                        resource_type="service_bay",
                        capacity=1,
                        active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "schedule_id": NORTHSTAR_SCHEDULE_ID.value,
                            "resource_type": "service_bay",
                            "capacity": 1,
                            "active": True,
                        },
                    )
                )
            for service_id in _SERVICE_IDS.values():
                for resource_id in NORTHSTAR_RESOURCE_IDS:
                    assignment_id = UUID(
                        bytes=bytes(
                            a ^ b
                            for a, b in zip(service_id.value.bytes, resource_id.bytes, strict=True)
                        )
                    )
                    await session.execute(
                        insert(ServiceResourceRow)
                        .values(
                            id=assignment_id,
                            tenant_id=NORTHSTAR_TENANT_ID.value,
                            service_id=service_id.value,
                            resource_id=resource_id,
                            required_capacity=1,
                            active=True,
                        )
                        .on_conflict_do_update(
                            constraint="uq_service_resources_tenant_id_service_id_resource_id",
                            set_={"required_capacity": 1, "active": True},
                        )
                    )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    asyncio.run(seed_northstar(database_url, os.environ.get("APP_ENV", "")))


if __name__ == "__main__":
    main()
