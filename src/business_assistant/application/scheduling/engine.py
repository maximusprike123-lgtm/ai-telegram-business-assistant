"""Pure deterministic weekly/override schedule evaluation."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from business_assistant.domain.scheduling import (
    BusinessSchedule,
    IntervalType,
    ScheduleInterval,
)

from ..common.errors import InvalidDateTimeError, InvalidScheduleError


@dataclass(frozen=True, slots=True)
class EffectiveDay:
    local_date: date
    intervals: tuple[tuple[time, time], ...]
    source: str
    reason: str | None = None


def _subtract_breaks(
    openings: list[ScheduleInterval], breaks: list[ScheduleInterval]
) -> tuple[tuple[time, time], ...]:
    result: list[tuple[time, time]] = []
    for opening in sorted(openings, key=lambda item: item.start_local):
        pieces = [(opening.start_local, opening.end_local)]
        for pause in sorted(breaks, key=lambda item: item.start_local):
            revised: list[tuple[time, time]] = []
            for start, end in pieces:
                if pause.end_local <= start or pause.start_local >= end:
                    revised.append((start, end))
                    continue
                if pause.start_local > start:
                    revised.append((start, pause.start_local))
                if pause.end_local < end:
                    revised.append((pause.end_local, end))
            pieces = revised
        result.extend(pieces)
    ordered = tuple(sorted(result))
    for previous, current in pairwise(ordered):
        if previous[1] > current[0]:
            raise InvalidScheduleError("Business intervals overlap")
    return ordered


def effective_day(schedule: BusinessSchedule, local_date: date) -> EffectiveDay:
    try:
        override = schedule.override_for(local_date)
    except Exception as exc:
        raise InvalidScheduleError("Multiple schedule overrides apply to one date") from exc
    if override is not None:
        if override.closed:
            return EffectiveDay(local_date, (), "override", override.reason)
        candidates = list(override.intervals)
        source = "override"
        reason = override.reason
    else:
        candidates = [item for item in schedule.intervals if item.weekday == local_date.weekday()]
        source = "weekly"
        reason = None
    openings = [item for item in candidates if item.interval_type is IntervalType.OPEN]
    breaks = [item for item in candidates if item.interval_type is IntervalType.BREAK]
    result = EffectiveDay(local_date, _subtract_breaks(openings, breaks), source, reason)
    zone = ZoneInfo(schedule.timezone)
    for start, end in result.intervals:
        opening = resolve_local_boundary(datetime.combine(local_date, start), zone, opening=True)
        closing = resolve_local_boundary(datetime.combine(local_date, end), zone, opening=False)
        if closing.astimezone(UTC) <= opening.astimezone(UTC):
            raise InvalidScheduleError("Business interval has no positive elapsed duration")
    return result


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidDateTimeError()
    return value


def is_open(schedule: BusinessSchedule, at: datetime) -> tuple[bool, datetime, EffectiveDay]:
    local = require_aware(at).astimezone(ZoneInfo(schedule.timezone))
    day = effective_day(schedule, local.date())
    wall_time = local.timetz().replace(tzinfo=None)
    return any(start <= wall_time < end for start, end in day.intervals), local, day


def _valid_local_candidates(naive: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        instant = aware.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            candidates[instant] = aware
    return tuple(candidates[key] for key in sorted(candidates))


def resolve_local_boundary(naive: datetime, zone: ZoneInfo, *, opening: bool) -> datetime:
    candidates = _valid_local_candidates(naive, zone)
    if not candidates:
        raise InvalidScheduleError("Schedule boundary falls in a nonexistent local time")
    return candidates[0] if opening else candidates[-1]


def next_opening(
    schedule: BusinessSchedule,
    at: datetime,
    *,
    search_horizon_days: int = 370,
) -> tuple[bool, datetime | None, datetime, int]:
    if not 1 <= search_horizon_days <= 730:
        raise InvalidScheduleError("Search horizon must be between 1 and 730 days")
    open_now, local, _ = is_open(schedule, at)
    if open_now:
        return True, None, local, 0
    zone = ZoneInfo(schedule.timezone)
    for offset in range(search_horizon_days + 1):
        local_date = local.date() + timedelta(days=offset)
        day = effective_day(schedule, local_date)
        for start, _ in day.intervals:
            if offset == 0 and start <= local.timetz().replace(tzinfo=None):
                continue
            candidate = resolve_local_boundary(
                datetime.combine(local_date, start), zone, opening=True
            )
            if candidate.astimezone(UTC) > at.astimezone(UTC):
                return False, candidate, local, offset
    return False, None, local, search_horizon_days
