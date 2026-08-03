from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class HoursIntervalDTO:
    start_local: str
    end_local: str


@dataclass(frozen=True, slots=True)
class BusinessDayDTO:
    date: date
    weekday: int
    day_label: str
    closed: bool
    intervals: tuple[HoursIntervalDTO, ...]
    source: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class BusinessStatusDTO:
    open_now: bool
    evaluated_at: datetime
    local_date: date
    local_time: str
    timezone: str


@dataclass(frozen=True, slots=True)
class NextOpeningDTO:
    open_now: bool
    next_opening_at: datetime | None
    next_opening_local: str | None
    timezone: str
    searched_days: int
