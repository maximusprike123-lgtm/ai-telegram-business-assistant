"""Tenant-authorized deterministic catalog queries."""

from business_assistant.domain.catalog import Service
from business_assistant.domain.shared import CategoryId, Locale, ServiceId
from business_assistant.domain.tenants import Tenant

from ..common.errors import CategoryNotFoundError, ServiceNotFoundError, TenantNotFoundError
from ..common.localization import (
    format_duration,
    format_price,
    locale_candidates,
    resolve_common_locale,
    resolve_localized,
)
from ..common.ports import Phase3UnitOfWorkFactory
from ..common.security import Permission, Principal
from .dto import PublicPriceDTO, ServiceCategoryDTO, ServiceDTO


def _tenant_locale_context(tenant: Tenant | None, requested: str | None) -> tuple[Locale, ...]:
    if tenant is None or not tenant.can_process_new_work:
        raise TenantNotFoundError()
    return locale_candidates(requested, tenant.default_locale, tenant.supported_locales)


def _service_dto(service: Service, candidates: tuple[Locale, ...]) -> ServiceDTO:
    resolved = resolve_common_locale((service.names, service.descriptions), candidates)
    minimum, maximum = service.price.minimum, service.price.maximum
    represented_money = minimum or maximum
    return ServiceDTO(
        id=str(service.id),
        category_id=str(service.category_id),
        code=service.code,
        name=service.names[resolved],
        description=service.descriptions[resolved],
        locale=resolved.value,
        duration_seconds=int(service.duration.total_seconds()),
        duration_display=format_duration(service.duration, resolved),
        price=PublicPriceDTO(
            mode=service.price.mode.value,
            currency=represented_money.currency if represented_money is not None else None,
            minimum_minor=minimum.amount_minor if minimum else None,
            maximum_minor=maximum.amount_minor if maximum else None,
            display=format_price(service.price, resolved),
        ),
        preparation_notes=service.preparation_notes.get(resolved),
        eligibility_notes=service.eligibility_notes.get(resolved),
        bookable=service.can_be_booked,
    )


class ListServiceCategories:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, principal: Principal, locale: str | None = None
    ) -> tuple[ServiceCategoryDTO, ...]:
        principal.require(Permission.CATALOG_READ)
        async with self._uow_factory() as uow:
            tenant = await uow.tenants.get(principal.tenant_id, principal.tenant_id)
            categories = await uow.categories.list_active(principal.tenant_id)
        candidates = _tenant_locale_context(tenant, locale)
        result = []
        for category in categories:
            name, resolved = resolve_localized(category.names, candidates)
            result.append(
                ServiceCategoryDTO(str(category.id), name, resolved.value, category.sort_order)
            )
        return tuple(result)


class ListServices:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        principal: Principal,
        locale: str | None = None,
        category_id: CategoryId | None = None,
    ) -> tuple[ServiceDTO, ...]:
        principal.require(Permission.CATALOG_READ)
        async with self._uow_factory() as uow:
            tenant = await uow.tenants.get(principal.tenant_id, principal.tenant_id)
            if (
                category_id is not None
                and await uow.categories.get_active(principal.tenant_id, category_id) is None
            ):
                raise CategoryNotFoundError()
            services = await uow.services.list_active(principal.tenant_id, category_id=category_id)
        candidates = _tenant_locale_context(tenant, locale)
        return tuple(_service_dto(service, candidates) for service in services)


class GetService:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, principal: Principal, service_id: ServiceId, locale: str | None = None
    ) -> ServiceDTO:
        principal.require(Permission.CATALOG_READ)
        async with self._uow_factory() as uow:
            tenant = await uow.tenants.get(principal.tenant_id, principal.tenant_id)
            service = await uow.services.get_active(principal.tenant_id, service_id)
        candidates = _tenant_locale_context(tenant, locale)
        if service is None:
            raise ServiceNotFoundError()
        return _service_dto(service, candidates)
