"""Pure tenant-local availability calculation."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from business_assistant.application.scheduling.engine import effective_day
from business_assistant.domain.shared import TimeRange

from .models import AvailabilityContext, AvailableResource, AvailableSlot


def _local_candidates(naive: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        instant = aware.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            candidates[instant] = aware
    return tuple(candidates[key] for key in sorted(candidates))


def _overlaps(first: TimeRange, second: TimeRange) -> bool:
    return first.start < second.end and second.start < first.end


def _has_capacity(resource: AvailableResource, occupied: TimeRange) -> bool:
    used = sum(
        period.capacity_used
        for period in resource.busy_periods
        if _overlaps(period.time_range, occupied)
    )
    return resource.active and used < resource.capacity


def calculate_availability(
    context: AvailabilityContext,
    *,
    local_date: date,
    now: datetime,
) -> tuple[AvailableSlot, ...]:
    """Return one deterministic slot per start time using the first eligible resource."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Availability clock must be timezone-aware")
    if not context.active or not context.bookable or not context.resources:
        return ()
    policy = context.policy
    earliest = now.astimezone(UTC) + policy.minimum_notice
    latest = now.astimezone(UTC) + policy.booking_horizon
    interval_seconds = int(policy.slot_interval.total_seconds())
    candidates: list[AvailableSlot] = []
    seen_starts: set[datetime] = set()
    for resource in sorted(context.resources, key=lambda item: str(item.id)):
        if not resource.active or not resource.schedule.active:
            continue
        zone = ZoneInfo(resource.schedule.timezone)
        day = effective_day(resource.schedule, local_date)
        for opening, closing in day.intervals:
            cursor = datetime.combine(local_date, opening)
            seconds = cursor.hour * 3600 + cursor.minute * 60 + cursor.second
            remainder = seconds % interval_seconds
            if remainder:
                cursor += timedelta(seconds=interval_seconds - remainder)
            closing_naive = datetime.combine(local_date, closing)
            while cursor < closing_naive:
                for local_start in _local_candidates(cursor, zone):
                    start = local_start.astimezone(UTC)
                    appointment_end = start + context.duration
                    occupied_end = appointment_end + context.cleanup_buffer
                    local_occupied_end = occupied_end.astimezone(zone)
                    if (
                        start < earliest
                        or start > latest
                        or local_occupied_end.date() != local_date
                        or local_occupied_end.replace(tzinfo=None) > closing_naive
                    ):
                        continue
                    occupied = TimeRange(start, occupied_end)
                    if start in seen_starts or not _has_capacity(resource, occupied):
                        continue
                    candidates.append(
                        AvailableSlot(
                            start,
                            appointment_end,
                            resource.id,
                            local_date,
                            local_start.strftime("%H:%M"),
                            resource.schedule.timezone,
                        )
                    )
                    seen_starts.add(start)
                cursor += policy.slot_interval
    return tuple(sorted(candidates, key=lambda item: (item.start_at, str(item.resource_id))))
