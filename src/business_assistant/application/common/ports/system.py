"""System capability ports, supplied by bootstrap/infrastructure in later phases."""

from datetime import datetime
from typing import Protocol, TypeVar

from business_assistant.domain.shared import EntityId

IdentifierT = TypeVar("IdentifierT", bound=EntityId, covariant=True)


class Clock(Protocol):
    def now(self) -> datetime:
        """Return a timezone-aware current instant."""
        ...


class IDGenerator(Protocol[IdentifierT]):
    def next_id(self) -> IdentifierT:
        """Return a new opaque identifier of the configured type."""
        ...
