"""Opaque UUID identifiers; identifier classes are intentionally not interchangeable."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EntityId:
    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)


class AggregateId(EntityId):
    """Generic aggregate identifier for infrastructure-neutral events."""


class TenantId(EntityId):
    pass


class CustomerId(EntityId):
    pass


class ConversationId(EntityId):
    pass


class ServiceId(EntityId):
    pass


class CategoryId(EntityId):
    pass


class ScheduleId(EntityId):
    pass


class BookingId(EntityId):
    pass


class BookingDraftId(EntityId):
    pass


class SlotHoldId(EntityId):
    pass


class ResourceId(EntityId):
    pass


class LeadId(EntityId):
    pass


class HandoffId(EntityId):
    pass


class DocumentId(EntityId):
    pass
