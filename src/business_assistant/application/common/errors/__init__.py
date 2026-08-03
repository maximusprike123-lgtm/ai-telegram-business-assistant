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
    CategoryNotFoundError,
    InvalidDateTimeError,
    InvalidScheduleError,
    PublicProfileNotFoundError,
    ServiceNotFoundError,
    TenantNotFoundError,
    UnresolvedLocaleError,
)

__all__ = [
    "ApplicationError",
    "AuthenticationError",
    "AuthorizationError",
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
    "TenantNotFoundError",
    "UnresolvedLocaleError",
]
