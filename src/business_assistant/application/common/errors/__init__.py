"""Application-facing persistence errors."""

from .persistence import (
    DuplicateEntityError,
    EntityNotFoundError,
    IntegrityConflictError,
    PersistenceError,
    StaleEntityError,
)

__all__ = [
    "DuplicateEntityError",
    "EntityNotFoundError",
    "IntegrityConflictError",
    "PersistenceError",
    "StaleEntityError",
]
