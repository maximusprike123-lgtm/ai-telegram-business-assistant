"""Read-side repository and unit-of-work contracts used by Phase 3 queries."""

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self

from business_assistant.domain.catalog import Service, ServiceCategory
from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import CategoryId, ScheduleId, ServiceId, TenantId
from business_assistant.domain.tenants import Tenant, TenantPublicProfile


class TenantQueryRepository(Protocol):
    async def get(self, tenant_id: TenantId, entity_id: TenantId) -> Tenant | None: ...


class PublicProfileQueryRepository(Protocol):
    async def get(self, tenant_id: TenantId) -> TenantPublicProfile | None: ...


class CategoryQueryRepository(Protocol):
    async def list_active(self, tenant_id: TenantId) -> Sequence[ServiceCategory]: ...

    async def get_active(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> ServiceCategory | None: ...


class ServiceQueryRepository(Protocol):
    async def list_active(
        self, tenant_id: TenantId, *, category_id: CategoryId | None
    ) -> Sequence[Service]: ...

    async def get_active(self, tenant_id: TenantId, service_id: ServiceId) -> Service | None: ...


class ScheduleQueryRepository(Protocol):
    async def get(self, tenant_id: TenantId, entity_id: ScheduleId) -> BusinessSchedule | None: ...


class Phase3UnitOfWork(Protocol):
    tenants: TenantQueryRepository
    public_profiles: PublicProfileQueryRepository
    categories: CategoryQueryRepository
    services: ServiceQueryRepository
    schedules: ScheduleQueryRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class Phase3UnitOfWorkFactory(Protocol):
    def __call__(self) -> Phase3UnitOfWork: ...
