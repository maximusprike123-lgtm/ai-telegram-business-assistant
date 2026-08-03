from datetime import UTC, date, datetime, time, timedelta

import pytest

from business_assistant.application.bookings import (
    AvailabilityContext,
    AvailableResource,
    BookingPolicy,
    BusyPeriod,
    calculate_availability,
)
from business_assistant.domain.scheduling import BusinessSchedule, ScheduleInterval
from business_assistant.domain.shared import ResourceId, ScheduleId, ServiceId, TenantId, TimeRange


def policy(**changes: object) -> BookingPolicy:
    values = {
        "slot_interval": timedelta(minutes=30),
        "booking_horizon": timedelta(days=30),
        "minimum_notice": timedelta(hours=2),
        "hold_duration": timedelta(minutes=5),
        "draft_duration": timedelta(minutes=30),
        "change_cutoff": timedelta(hours=24),
        "customer_name_max_length": 100,
        "customer_phone_max_length": 32,
        "customer_note_max_length": 500,
    }
    values.update(changes)
    return BookingPolicy(**values)  # type: ignore[arg-type]


def context(
    *,
    timezone: str = "Europe/Moscow",
    intervals: tuple[ScheduleInterval, ...] | None = None,
    busy: tuple[BusyPeriod, ...] = (),
    capacity: int = 1,
    resource_active: bool = True,
    service_active: bool = True,
    bookable: bool = True,
    duration: timedelta = timedelta(hours=1),
    cleanup: timedelta = timedelta(minutes=10),
    booking_policy: BookingPolicy | None = None,
) -> AvailabilityContext:
    tenant_id = TenantId.new()
    schedule = BusinessSchedule(
        ScheduleId.new(),
        tenant_id,
        "Workshop",
        timezone,
        intervals or (ScheduleInterval(0, time(9), time(12)),),
    )
    return AvailabilityContext(
        tenant_id,
        ServiceId.new(),
        "Inspection",
        duration,
        cleanup,
        service_active,
        bookable,
        booking_policy or policy(),
        (AvailableResource(ResourceId.new(), schedule, capacity, resource_active, busy),),
    )


def test_normal_availability_is_local_ordered_and_respects_closing_buffer() -> None:
    result = calculate_availability(
        context(),
        local_date=date(2026, 8, 3),
        now=datetime(2026, 8, 3, 4, tzinfo=UTC),
    )
    assert [slot.local_time for slot in result] == ["09:00", "09:30", "10:00", "10:30"]
    assert all(slot.timezone == "Europe/Moscow" for slot in result)
    assert all(slot.start_at < slot.end_at for slot in result)


def test_closed_inactive_unbookable_and_no_resource_return_no_slots() -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    assert calculate_availability(context(), local_date=date(2026, 8, 4), now=now) == ()
    assert (
        calculate_availability(context(service_active=False), local_date=date(2026, 8, 3), now=now)
        == ()
    )
    assert (
        calculate_availability(context(bookable=False), local_date=date(2026, 8, 3), now=now) == ()
    )
    assert (
        calculate_availability(context(resource_active=False), local_date=date(2026, 8, 3), now=now)
        == ()
    )


def test_notice_horizon_duration_and_capacity_conflicts_are_enforced() -> None:
    selected_date = date(2026, 8, 3)
    now = datetime(2026, 8, 3, 6, 30, tzinfo=UTC)
    full = BusyPeriod(
        TimeRange(datetime(2026, 8, 3, 7, tzinfo=UTC), datetime(2026, 8, 3, 8, tzinfo=UTC))
    )
    slots = calculate_availability(
        context(busy=(full,), booking_policy=policy(minimum_notice=timedelta(minutes=1))),
        local_date=selected_date,
        now=now,
    )
    assert "10:00" not in {slot.local_time for slot in slots}
    pooled = calculate_availability(
        context(
            busy=(full,),
            capacity=2,
            booking_policy=policy(minimum_notice=timedelta(minutes=1)),
        ),
        local_date=selected_date,
        now=now,
    )
    assert "10:00" in {slot.local_time for slot in pooled}
    assert (
        calculate_availability(
            context(duration=timedelta(hours=4)), local_date=selected_date, now=now
        )
        == ()
    )
    assert (
        calculate_availability(
            context(booking_policy=policy(booking_horizon=timedelta(days=1))),
            local_date=date(2026, 8, 10),
            now=now,
        )
        == ()
    )


def test_dst_gap_is_skipped_and_overlap_is_deterministic() -> None:
    spring = context(
        timezone="America/New_York",
        intervals=(ScheduleInterval(6, time(1), time(4)),),
        duration=timedelta(minutes=30),
        cleanup=timedelta(),
        booking_policy=policy(minimum_notice=timedelta(minutes=1)),
    )
    gap = calculate_availability(
        spring,
        local_date=date(2026, 3, 8),
        now=datetime(2026, 3, 7, tzinfo=UTC),
    )
    assert "02:00" not in {slot.local_time for slot in gap}
    fall = context(
        timezone="America/New_York",
        intervals=(ScheduleInterval(6, time(0), time(3)),),
        duration=timedelta(minutes=30),
        cleanup=timedelta(),
        booking_policy=policy(minimum_notice=timedelta(minutes=1)),
    )
    overlap = calculate_availability(
        fall,
        local_date=date(2026, 11, 1),
        now=datetime(2026, 10, 31, tzinfo=UTC),
    )
    assert [slot.local_time for slot in overlap].count("01:00") == 2
    assert list(overlap) == sorted(overlap, key=lambda item: (item.start_at, str(item.resource_id)))


def test_booking_policy_validation_is_bounded() -> None:
    with pytest.raises(ValueError, match="durations"):
        policy(slot_interval=timedelta())
    with pytest.raises(ValueError, match="cutoff"):
        policy(change_cutoff=timedelta(minutes=-1))
    with pytest.raises(ValueError, match="name"):
        policy(customer_name_max_length=0)
    with pytest.raises(ValueError, match="phone"):
        policy(customer_phone_max_length=7)
    with pytest.raises(ValueError, match="note"):
        policy(customer_note_max_length=2001)
