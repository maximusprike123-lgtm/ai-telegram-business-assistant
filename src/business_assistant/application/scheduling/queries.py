"""Authorized business-hours/status/next-opening queries."""

from datetime import date, datetime, timedelta

from business_assistant.application.common.ports import Clock, Phase3UnitOfWorkFactory
from business_assistant.domain.scheduling import BusinessSchedule

from ..common.errors import (
    InvalidDateTimeError,
    InvalidScheduleError,
    PublicProfileNotFoundError,
    TenantNotFoundError,
    UnresolvedLocaleError,
)
from ..common.localization import locale_candidates
from ..common.security import Permission, Principal
from .dto import BusinessDayDTO, BusinessStatusDTO, HoursIntervalDTO, NextOpeningDTO
from .engine import effective_day, is_open, next_opening, require_aware

_DAY_LABELS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}


def business_hours_dtos(
    schedule: BusinessSchedule, start_date: date, days: int, locale: str
) -> tuple[BusinessDayDTO, ...]:
    labels = _DAY_LABELS.get(locale)
    if labels is None:
        raise UnresolvedLocaleError()
    result = []
    for offset in range(days):
        day = effective_day(schedule, start_date + timedelta(days=offset))
        result.append(
            BusinessDayDTO(
                date=day.local_date,
                weekday=day.local_date.weekday(),
                day_label=labels[day.local_date.weekday()],
                closed=not day.intervals,
                intervals=tuple(
                    HoursIntervalDTO(
                        start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")
                    )
                    for start, end in day.intervals
                ),
                source=day.source,
                reason=day.reason,
            )
        )
    return tuple(result)


def business_status_dto(schedule: BusinessSchedule, instant: datetime) -> BusinessStatusDTO:
    open_now, local, _ = is_open(schedule, instant)
    return BusinessStatusDTO(
        open_now, instant, local.date(), local.isoformat(timespec="minutes"), schedule.timezone
    )


def next_opening_dto(
    schedule: BusinessSchedule, instant: datetime, horizon: int = 370
) -> NextOpeningDTO:
    open_now, next_at, _, searched = next_opening(schedule, instant, search_horizon_days=horizon)
    return NextOpeningDTO(
        open_now=open_now,
        next_opening_at=next_at,
        next_opening_local=next_at.isoformat(timespec="minutes") if next_at else None,
        timezone=schedule.timezone,
        searched_days=searched,
    )


async def _load_schedule(
    uow_factory: Phase3UnitOfWorkFactory, principal: Principal
) -> tuple[BusinessSchedule, str, frozenset[str], str]:
    async with uow_factory() as uow:
        tenant = await uow.tenants.get(principal.tenant_id, principal.tenant_id)
        if tenant is None or not tenant.can_process_new_work:
            raise TenantNotFoundError()
        profile = await uow.public_profiles.get(principal.tenant_id)
        if profile is None:
            raise PublicProfileNotFoundError()
        schedule = await uow.schedules.get(principal.tenant_id, profile.schedule_id)
    if schedule is None or not schedule.active:
        raise PublicProfileNotFoundError()
    if schedule.timezone != tenant.timezone:
        raise InvalidScheduleError("Business schedule timezone does not match tenant timezone")
    return (
        schedule,
        tenant.default_locale.value,
        frozenset(item.value for item in tenant.supported_locales),
        tenant.timezone,
    )


class GetBusinessHours:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        principal: Principal,
        start_date: date,
        *,
        days: int = 7,
        locale: str | None = None,
    ) -> tuple[BusinessDayDTO, ...]:
        principal.require(Permission.SCHEDULE_READ)
        if not 1 <= days <= 31:
            raise InvalidDateTimeError("Hours range must be between 1 and 31 days")
        schedule, default, supported, _ = await _load_schedule(self._uow_factory, principal)
        from business_assistant.domain.shared import Locale

        resolved = locale_candidates(
            locale, Locale(default), frozenset(Locale(x) for x in supported)
        )[0]
        return business_hours_dtos(schedule, start_date, days, resolved.value)


class GetBusinessStatus:
    def __init__(self, uow_factory: Phase3UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(self, principal: Principal, at: datetime | None = None) -> BusinessStatusDTO:
        principal.require(Permission.SCHEDULE_READ)
        instant = require_aware(at if at is not None else self._clock.now())
        schedule, _, _, _ = await _load_schedule(self._uow_factory, principal)
        return business_status_dto(schedule, instant)


class GetNextOpening:
    def __init__(
        self,
        uow_factory: Phase3UnitOfWorkFactory,
        clock: Clock,
        *,
        search_horizon_days: int = 370,
    ) -> None:
        self._uow_factory, self._clock = uow_factory, clock
        self._horizon = search_horizon_days

    async def execute(self, principal: Principal, at: datetime | None = None) -> NextOpeningDTO:
        principal.require(Permission.SCHEDULE_READ)
        instant = require_aware(at if at is not None else self._clock.now())
        schedule, _, _, _ = await _load_schedule(self._uow_factory, principal)
        return next_opening_dto(schedule, instant, self._horizon)
