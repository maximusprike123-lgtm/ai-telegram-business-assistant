from datetime import UTC, datetime


class UTCClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
