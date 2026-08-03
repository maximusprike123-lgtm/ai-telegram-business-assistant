from business_assistant.application.common.ports import Clock, Phase3UnitOfWorkFactory
from business_assistant.domain.shared import Locale

from ..common.errors import InvalidScheduleError, PublicProfileNotFoundError, TenantNotFoundError
from ..common.localization import locale_candidates, resolve_localized
from ..common.security import Permission, Principal
from ..scheduling.engine import require_aware
from ..scheduling.queries import business_hours_dtos, business_status_dto, next_opening_dto
from .dto import TenantPublicProfileDTO


def _optional_localized(values: dict[Locale, str], candidates: tuple[Locale, ...]) -> str | None:
    for locale in candidates:
        value = values.get(locale)
        if value:
            return value
    return None


class GetTenantPublicProfile:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(
        self, principal: Principal, locale: str | None = None
    ) -> TenantPublicProfileDTO:
        principal.require(Permission.PUBLIC_PROFILE_READ)
        async with self._uow_factory() as uow:
            tenant = await uow.tenants.get(principal.tenant_id, principal.tenant_id)
            profile = await uow.public_profiles.get(principal.tenant_id)
            schedule = (
                await uow.schedules.get(principal.tenant_id, profile.schedule_id)
                if profile is not None
                else None
            )
        if tenant is None or not tenant.can_process_new_work:
            raise TenantNotFoundError()
        if profile is None:
            raise PublicProfileNotFoundError()
        if schedule is None or not schedule.active:
            raise PublicProfileNotFoundError()
        if schedule.timezone != tenant.timezone:
            raise InvalidScheduleError("Business schedule timezone does not match tenant timezone")
        candidates = locale_candidates(locale, tenant.default_locale, tenant.supported_locales)
        description, resolved = resolve_localized(profile.descriptions, candidates)
        instant = require_aware(self._clock.now())
        status = business_status_dto(schedule, instant)
        next_opening = next_opening_dto(schedule, instant)
        hours = business_hours_dtos(schedule, status.local_date, 7, resolved.value)
        return TenantPublicProfileDTO(
            name=tenant.name,
            description=description,
            locale=resolved.value,
            default_locale=tenant.default_locale.value,
            supported_locales=tuple(sorted(item.value for item in tenant.supported_locales)),
            timezone=tenant.timezone,
            public_phone=profile.public_phone,
            public_email=profile.public_email,
            website_url=profile.website_url,
            address=_optional_localized(profile.addresses, candidates),
            service_area=_optional_localized(profile.service_areas, candidates),
            parking_guidance=_optional_localized(profile.parking_guidance, candidates),
            payment_methods=profile.payment_methods,
            warranty_policy=_optional_localized(profile.warranty_policy, candidates),
            appointment_policy=_optional_localized(profile.appointment_policy, candidates),
            business_hours=hours,
            status=status,
            next_opening=next_opening,
        )
