"""Stable errors exposed by persistence ports instead of adapter exceptions."""

from dataclasses import dataclass


@dataclass(eq=False)
class PersistenceError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class DuplicateEntityError(PersistenceError):
    def __init__(self, entity: str) -> None:
        super().__init__("persistence.duplicate", f"{entity} already exists")


class EntityNotFoundError(PersistenceError):
    def __init__(self, entity: str) -> None:
        super().__init__("persistence.not_found", f"{entity} was not found")


class StaleEntityError(PersistenceError):
    def __init__(self, entity: str) -> None:
        super().__init__("persistence.stale", f"{entity} was changed by another transaction")


class IntegrityConflictError(PersistenceError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "persistence.integrity_conflict",
            f"{operation} conflicts with persisted business constraints",
        )
