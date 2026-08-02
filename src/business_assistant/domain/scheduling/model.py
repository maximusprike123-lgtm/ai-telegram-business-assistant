from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..shared import ScheduleId, TenantId, ValidationError


class IntervalType(StrEnum):
    OPEN = "open"
    BREAK = "break"


@dataclass(frozen=True, slots=True)
class ScheduleInterval:
    weekday: int
    start_local: time
    end_local: time
    interval_type: IntervalType = IntervalType.OPEN

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6:
            raise ValidationError("Weekday must be in the range Monday=0 to Sunday=6")
        if self.start_local.tzinfo is not None or self.end_local.tzinfo is not None:
            raise ValidationError("Schedule interval times must be local wall-clock values")
        if self.start_local >= self.end_local:
            raise ValidationError("Schedule interval start must precede end")


@dataclass(frozen=True, slots=True)
class ScheduleOverride:
    starts_on: date
    ends_on: date
    closed: bool
    intervals: tuple[ScheduleInterval, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.starts_on > self.ends_on:
            raise ValidationError("Schedule override start date must not follow end date")
        if self.closed and self.intervals:
            raise ValidationError("A closed override cannot contain opening intervals")
        if not self.closed and not self.intervals:
            raise ValidationError("An open override requires at least one interval")

    def applies_on(self, local_date: date) -> bool:
        return self.starts_on <= local_date <= self.ends_on


@dataclass(slots=True)
class BusinessSchedule:
    id: ScheduleId
    tenant_id: TenantId
    name: str
    timezone: str
    intervals: tuple[ScheduleInterval, ...] = ()
    overrides: tuple[ScheduleOverride, ...] = ()
    active: bool = True
    _zone: ZoneInfo = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("Schedule name is required")
        try:
            self._zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError("Schedule timezone must be a valid IANA timezone") from exc
        self._validate_intervals()

    def _validate_intervals(self) -> None:
        for weekday in range(7):
            openings = sorted(
                (
                    item
                    for item in self.intervals
                    if item.weekday == weekday and item.interval_type is IntervalType.OPEN
                ),
                key=lambda item: item.start_local,
            )
            for previous, current in pairwise(openings):
                if previous.end_local > current.start_local:
                    raise ValidationError("Opening intervals cannot overlap")
            for break_interval in (
                item
                for item in self.intervals
                if item.weekday == weekday and item.interval_type is IntervalType.BREAK
            ):
                if not any(
                    opening.start_local <= break_interval.start_local
                    and break_interval.end_local <= opening.end_local
                    for opening in openings
                ):
                    raise ValidationError("Break intervals must be contained within opening hours")

    def override_for(self, local_date: date) -> ScheduleOverride | None:
        matches = [override for override in self.overrides if override.applies_on(local_date)]
        if len(matches) > 1:
            raise ValidationError("Multiple schedule overrides apply to the same local date")
        return matches[0] if matches else None
