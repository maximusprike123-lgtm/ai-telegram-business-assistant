"""Application-facing persistence errors."""

from .persistence import (
    DuplicateEntityError,
    EntityNotFoundError,
    IntegrityConflictError,
    PersistenceError,
    StaleEntityError,
)
from .queries import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    BookingConflictError,
    BookingExpiredError,
    BookingNotFoundError,
    BookingPolicyError,
    CategoryNotFoundError,
    InvalidDateTimeError,
    InvalidScheduleError,
    PublicProfileNotFoundError,
    ServiceNotFoundError,
    TelegramIdentityUnavailableError,
    TenantNotFoundError,
    UnresolvedLocaleError,
)

__all__ = [
    "ApplicationError",
    "AuthenticationError",
    "AuthorizationError",
    "BookingConflictError",
    "BookingExpiredError",
    "BookingNotFoundError",
    "BookingPolicyError",
    "CategoryNotFoundError",
    "DuplicateEntityError",
    "EntityNotFoundError",
    "IntegrityConflictError",
    "InvalidDateTimeError",
    "InvalidScheduleError",
    "PersistenceError",
    "PublicProfileNotFoundError",
    "ServiceNotFoundError",
    "StaleEntityError",
    "TelegramIdentityUnavailableError",
    "TenantNotFoundError",
    "UnresolvedLocaleError",
]
