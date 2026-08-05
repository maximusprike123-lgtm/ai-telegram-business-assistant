"""Low-cardinality operational vocabulary and safe dependency status."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Component(StrEnum):
    HTTP = "http"
    TELEGRAM = "telegram"
    AI = "ai"
    RETRIEVAL = "retrieval"
    BOOKING = "booking"
    HANDOFF = "handoff"
    OUTBOX = "outbox"
    NOTIFICATION = "notification"
    CELERY = "celery"
    DATABASE = "database"


class Operation(StrEnum):
    REQUEST = "request"
    UPDATE = "update"
    EXECUTE = "execute"
    SEARCH = "search"
    AVAILABILITY = "availability"
    WORKFLOW = "workflow"
    DISPATCH = "dispatch"
    DELIVER = "deliver"
    TASK = "task"
    HEALTH_CHECK = "health_check"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


class DependencyStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    status: DependencyStatus
    required: bool
    latency_ms: int
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.name not in {"postgresql", "pgvector", "redis", "telegram", "ai_provider"}:
            raise ValueError("Dependency name is unsupported")
        if self.latency_ms < 0:
            raise ValueError("Dependency latency cannot be negative")


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    ready: bool
    checked_at: datetime
    dependencies: tuple[DependencyCheck, ...]

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("Diagnostic time must be timezone-aware")
