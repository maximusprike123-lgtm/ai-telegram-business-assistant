from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from business_assistant.application.common.errors import InvalidDateTimeError, InvalidScheduleError
from business_assistant.application.scheduling.engine import (
    effective_day,
    is_open,
    next_opening,
    resolve_local_boundary,
)
from business_assistant.domain.scheduling import (
    BusinessSchedule,
    ScheduleInterval,
    ScheduleOverride,
)
from business_assistant.domain.shared import ScheduleId, TenantId


def schedule(
    timezone: str = "Europe/Moscow",
    intervals: tuple[ScheduleInterval, ...] | None = None,
    overrides: tuple[ScheduleOverride, ...] = (),
) -> BusinessSchedule:
    return BusinessSchedule(
        ScheduleId.new(),
        TenantId.new(),
        "Hours",
        timezone,
        intervals
        if intervals is not None
        else (
            ScheduleInterval(0, time(8), time(12)),
            ScheduleInterval(0, time(13), time(18)),
        ),
        overrides,
    )


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 8, 3, 4, 59, tzinfo=UTC), False),
        (datetime(2026, 8, 3, 5, 30, tzinfo=UTC), True),
        (datetime(2026, 8, 3, 9, 30, tzinfo=UTC), False),
        (datetime(2026, 8, 3, 10, 30, tzinfo=UTC), True),
        (datetime(2026, 8, 3, 15, 1, tzinfo=UTC), False),
    ],
)
def test_open_closed_before_after_and_during_break(instant: datetime, expected: bool) -> None:
    assert is_open(schedule(), instant)[0] is expected


def test_next_opening_after_break_and_regular_closed_day() -> None:
    current = datetime(2026, 8, 3, 9, 30, tzinfo=UTC)
    open_now, result, _, searched = next_opening(schedule(), current)
    assert not open_now
    assert result == datetime(2026, 8, 3, 13, tzinfo=ZoneInfo("Europe/Moscow"))
    assert searched == 0

    sunday = datetime(2026, 8, 2, 12, tzinfo=UTC)
    assert next_opening(schedule(), sunday)[1] == datetime(
        2026, 8, 3, 8, tzinfo=ZoneInfo("Europe/Moscow")
    )


def test_open_now_returns_no_future_opening() -> None:
    result = next_opening(schedule(), datetime(2026, 8, 3, 6, tzinfo=UTC))
    assert result[0]
    assert result[1] is None


def test_closure_and_special_opening_overrides_replace_weekly_hours() -> None:
    closure = ScheduleOverride(date(2026, 8, 3), date(2026, 8, 3), True, reason="Holiday")
    special = ScheduleOverride(
        date(2026, 8, 4),
        date(2026, 8, 4),
        False,
        (ScheduleInterval(1, time(10), time(14)),),
        "Special",
    )
    configured = schedule(overrides=(closure, special))
    assert effective_day(configured, date(2026, 8, 3)).intervals == ()
    assert effective_day(configured, date(2026, 8, 4)).intervals == ((time(10), time(14)),)


def test_next_opening_crosses_month_year_and_exhausts_horizon() -> None:
    january_first = schedule(
        intervals=(ScheduleInterval(4, time(9), time(10)),)
    )  # Friday, 2027-01-01
    result = next_opening(january_first, datetime(2026, 12, 31, 20, tzinfo=UTC))
    assert result[1] is not None and result[1].date() == date(2027, 1, 1)
    empty = schedule(intervals=())
    assert next_opening(empty, datetime(2026, 12, 31, tzinfo=UTC), search_horizon_days=2)[1] is None


def test_utc_to_local_date_conversion_around_midnight() -> None:
    sunday = schedule(intervals=(ScheduleInterval(6, time(0), time(1)),))
    open_now, local, _ = is_open(sunday, datetime(2026, 8, 1, 21, 30, tzinfo=UTC))
    assert local.date() == date(2026, 8, 2)
    assert open_now


def test_spring_forward_schedule_and_nonexistent_boundary_policy() -> None:
    zone = "America/New_York"
    spanning = schedule(zone, (ScheduleInterval(6, time(1), time(4)),))
    assert is_open(spanning, datetime(2026, 3, 8, 7, 30, tzinfo=UTC))[0]
    nonexistent = schedule(zone, (ScheduleInterval(6, time(2, 30), time(4)),))
    with pytest.raises(InvalidScheduleError, match="nonexistent"):
        next_opening(nonexistent, datetime(2026, 3, 8, 5, tzinfo=UTC))


def test_fall_back_policy_uses_widest_interval_and_both_folds_are_open() -> None:
    zone = ZoneInfo("America/New_York")
    configured = schedule(str(zone), (ScheduleInterval(6, time(1, 30), time(2, 30)),))
    first_fold = datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0)
    second_fold = datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=1)
    assert is_open(configured, first_fold)[0]
    assert is_open(configured, second_fold)[0]
    naive = datetime(2026, 11, 1, 1, 30)
    assert resolve_local_boundary(naive, zone, opening=True).fold == 0
    assert resolve_local_boundary(naive, zone, opening=False).fold == 1


def test_naive_instant_and_invalid_horizon_are_rejected() -> None:
    with pytest.raises(InvalidDateTimeError):
        is_open(schedule(), datetime(2026, 8, 3, 10))
    with pytest.raises(InvalidScheduleError):
        next_opening(schedule(), datetime(2026, 8, 3, tzinfo=UTC), search_horizon_days=0)
