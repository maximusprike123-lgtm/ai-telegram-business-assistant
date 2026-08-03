from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.tenants import GetTenantPublicProfile
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
from business_assistant.infrastructure.security import StaticApiKeyAuthenticator
from business_assistant.presentation.http import Phase3ApiServices


@dataclass(frozen=True)
class FixedClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


class FakeTenantRepository:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant

    async def get(self, tenant_id: TenantId, entity_id: TenantId) -> Tenant | None:
        return self.tenant if tenant_id == entity_id == self.tenant.id else None


class FakeProfileRepository:
    def __init__(self, profile: TenantPublicProfile) -> None:
        self.profile = profile

    async def get(self, tenant_id: TenantId) -> TenantPublicProfile | None:
        return self.profile if tenant_id == self.profile.tenant_id else None


class FakeCategoryRepository:
    def __init__(self, categories: list[ServiceCategory]) -> None:
        self.categories = categories

    async def list_active(self, tenant_id: TenantId) -> list[ServiceCategory]:
        return sorted(
            [item for item in self.categories if item.tenant_id == tenant_id and item.active],
            key=lambda item: (item.sort_order, str(item.id)),
        )

    async def get_active(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> ServiceCategory | None:
        return next(
            (
                item
                for item in self.categories
                if item.tenant_id == tenant_id and item.id == category_id and item.active
            ),
            None,
        )


class FakeServiceRepository:
    def __init__(self, services: list[Service], categories: list[ServiceCategory]) -> None:
        self.services, self.categories = services, categories

    async def list_active(
        self, tenant_id: TenantId, *, category_id: CategoryId | None
    ) -> list[Service]:
        active_categories = {item.id for item in self.categories if item.active}
        return sorted(
            [
                item
                for item in self.services
                if item.tenant_id == tenant_id
                and item.active
                and item.category_id in active_categories
                and (category_id is None or item.category_id == category_id)
            ],
            key=lambda item: (item.code, str(item.id)),
        )

    async def get_active(self, tenant_id: TenantId, service_id: ServiceId) -> Service | None:
        active_categories = {item.id for item in self.categories if item.active}
        return next(
            (
                item
                for item in self.services
                if item.tenant_id == tenant_id
                and item.id == service_id
                and item.active
                and item.category_id in active_categories
            ),
            None,
        )


class FakeScheduleRepository:
    def __init__(self, schedule: BusinessSchedule) -> None:
        self.schedule = schedule

    async def get(self, tenant_id: TenantId, entity_id: ScheduleId) -> BusinessSchedule | None:
        return (
            self.schedule
            if tenant_id == self.schedule.tenant_id and entity_id == self.schedule.id
            else None
        )


class FakePhase3Uow:
    def __init__(
        self,
        tenant: Tenant,
        profile: TenantPublicProfile,
        categories: list[ServiceCategory],
        services: list[Service],
        schedule: BusinessSchedule,
    ) -> None:
        self.tenants = FakeTenantRepository(tenant)
        self.public_profiles = FakeProfileRepository(profile)
        self.categories = FakeCategoryRepository(categories)
        self.services = FakeServiceRepository(services, categories)
        self.schedules = FakeScheduleRepository(schedule)
        self.enter_count = 0

    async def __aenter__(self) -> "FakePhase3Uow":
        self.enter_count += 1
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None


def phase3_fixture() -> tuple[FakePhase3Uow, Principal, FixedClock, str]:
    tenant_id = TenantId.new()
    schedule_id = ScheduleId.new()
    active_category = ServiceCategory(CategoryId.new(), tenant_id, {Locale.EN: "Care"}, 1)
    inactive_category = ServiceCategory(
        CategoryId.new(), tenant_id, {Locale.EN: "Hidden"}, 0, False
    )

    def service(
        code: str,
        category_id: CategoryId,
        price: PricePresentation,
        *,
        active: bool = True,
    ) -> Service:
        return Service(
            ServiceId.new(),
            tenant_id,
            category_id,
            code,
            {Locale.EN: f"{code} service"},
            {Locale.EN: "English description"},
            timedelta(minutes=90),
            price,
            active=active,
        )

    services = [
        service(
            "exact", active_category.id, PricePresentation(PriceMode.EXACT, Money(125_050, "RUB"))
        ),
        service(
            "starting",
            active_category.id,
            PricePresentation(PriceMode.STARTING_FROM, Money(200_000, "RUB")),
        ),
        service("quote", active_category.id, PricePresentation(PriceMode.QUOTE_REQUIRED)),
        service(
            "inactive-service",
            active_category.id,
            PricePresentation(PriceMode.QUOTE_REQUIRED),
            active=False,
        ),
        service(
            "hidden-category", inactive_category.id, PricePresentation(PriceMode.QUOTE_REQUIRED)
        ),
    ]
    intervals = (
        *(
            interval
            for weekday in range(5)
            for interval in (
                ScheduleInterval(weekday, time(8), time(12)),
                ScheduleInterval(weekday, time(13), time(18)),
            )
        ),
        ScheduleInterval(5, time(9), time(15)),
    )
    schedule = BusinessSchedule(
        schedule_id,
        tenant_id,
        "Public hours",
        "Europe/Moscow",
        intervals,
        (
            ScheduleOverride(date(2026, 12, 31), date(2026, 12, 31), True, reason="Holiday"),
            ScheduleOverride(
                date(2027, 1, 3),
                date(2027, 1, 3),
                False,
                (ScheduleInterval(6, time(10), time(14)),),
                "Special hours",
            ),
        ),
    )
    tenant = Tenant(
        tenant_id,
        "demo-shop",
        "Demo Shop",
        "Europe/Moscow",
        Locale.EN,
        frozenset({Locale.EN}),
    )
    profile = TenantPublicProfile(
        tenant_id,
        schedule_id,
        {Locale.EN: "Demo description"},
        addresses={Locale.EN: "Demo address"},
    )
    uow = FakePhase3Uow(tenant, profile, [inactive_category, active_category], services, schedule)
    principal = Principal("tester", tenant_id, Role.VIEWER)
    clock = FixedClock(datetime(2026, 8, 3, 6, 30, tzinfo=UTC))
    return uow, principal, clock, "phase3-local-key"


def api_services(
    uow: FakePhase3Uow, principal: Principal, clock: FixedClock, key: str
) -> Phase3ApiServices:
    return Phase3ApiServices(
        GetTenantPublicProfile(lambda: uow, clock),
        ListServiceCategories(lambda: uow),
        ListServices(lambda: uow),
        GetService(lambda: uow),
        GetBusinessHours(lambda: uow),
        GetBusinessStatus(lambda: uow, clock),
        GetNextOpening(lambda: uow, clock),
        StaticApiKeyAuthenticator(key, principal),
    )
