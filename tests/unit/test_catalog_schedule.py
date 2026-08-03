from datetime import date, time, timedelta
from typing import cast

import pytest

from business_assistant.domain.catalog import Service
from business_assistant.domain.scheduling import (
    BusinessSchedule,
    IntervalType,
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
    ValidationError,
)


def make_service(tenant_id: TenantId, service_id: ServiceId, **overrides: object) -> Service:
    values: dict[str, object] = {
        "id": service_id,
        "tenant_id": tenant_id,
        "category_id": CategoryId.new(),
        "code": "brake-inspection",
        "names": {Locale.EN: "Brake inspection"},
        "descriptions": {Locale.EN: "Inspection"},
        "duration": timedelta(minutes=45),
        "price": PricePresentation(PriceMode.STARTING_FROM, Money(5000, "RUB")),
    }
    values.update(overrides)
    return Service(**values)  # type: ignore[arg-type]


def test_service_validates_duration_and_localization(
    tenant_id: TenantId, service_id: ServiceId
) -> None:
    service = make_service(tenant_id, service_id)
    assert service.can_be_booked
    with pytest.raises(ValidationError):
        make_service(tenant_id, service_id, duration=timedelta())
    with pytest.raises(ValidationError):
        make_service(tenant_id, service_id, names={Locale.EN: ""})
    with pytest.raises(ValidationError):
        unsupported = cast(Locale, "unsupported")
        make_service(
            tenant_id,
            service_id,
            names={Locale.EN: "Inspection"},
            descriptions={unsupported: "Unsupported locale description"},
        )


def test_archived_service_is_not_bookable(tenant_id: TenantId, service_id: ServiceId) -> None:
    service = make_service(tenant_id, service_id)
    service.archive()
    assert not service.active
    assert not service.can_be_booked


def test_schedule_interval_validates_wall_clock() -> None:
    interval = ScheduleInterval(0, time(8), time(18))
    assert interval.interval_type is IntervalType.OPEN
    with pytest.raises(ValidationError):
        ScheduleInterval(7, time(8), time(18))
    with pytest.raises(ValidationError):
        ScheduleInterval(0, time(18), time(8))


def test_business_schedule_validates_break_containment(tenant_id: TenantId) -> None:
    open_hours = ScheduleInterval(0, time(8), time(18))
    lunch = ScheduleInterval(0, time(12), time(13), IntervalType.BREAK)
    schedule = BusinessSchedule(
        ScheduleId.new(), tenant_id, "Workshop", "Europe/Moscow", (open_hours, lunch)
    )
    assert schedule.active
    with pytest.raises(ValidationError):
        BusinessSchedule(
            ScheduleId.new(),
            tenant_id,
            "Workshop",
            "Europe/Moscow",
            (open_hours, ScheduleInterval(0, time(7), time(9), IntervalType.BREAK)),
        )


def test_business_schedule_rejects_overlapping_openings(tenant_id: TenantId) -> None:
    with pytest.raises(ValidationError):
        BusinessSchedule(
            ScheduleId.new(),
            tenant_id,
            "Workshop",
            "Europe/Moscow",
            (
                ScheduleInterval(0, time(8), time(12)),
                ScheduleInterval(0, time(11), time(18)),
            ),
        )


def test_schedule_override_rules_and_lookup(tenant_id: TenantId) -> None:
    holiday = ScheduleOverride(date(2026, 8, 3), date(2026, 8, 3), True, reason="Holiday")
    schedule = BusinessSchedule(
        ScheduleId.new(), tenant_id, "Workshop", "Europe/Moscow", overrides=(holiday,)
    )
    assert schedule.override_for(date(2026, 8, 3)) == holiday
    assert schedule.override_for(date(2026, 8, 4)) is None
    with pytest.raises(ValidationError):
        ScheduleOverride(date(2026, 8, 4), date(2026, 8, 3), True)
    with pytest.raises(ValidationError):
        ScheduleOverride(date(2026, 8, 3), date(2026, 8, 3), False)


def test_schedule_rejects_duplicate_applicable_overrides(tenant_id: TenantId) -> None:
    first = ScheduleOverride(date(2026, 8, 3), date(2026, 8, 5), True)
    second = ScheduleOverride(date(2026, 8, 4), date(2026, 8, 4), True)
    schedule = BusinessSchedule(
        ScheduleId.new(), tenant_id, "Workshop", "Europe/Moscow", overrides=(first, second)
    )
    with pytest.raises(ValidationError):
        schedule.override_for(date(2026, 8, 4))
