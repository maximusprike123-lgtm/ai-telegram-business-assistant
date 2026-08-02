"""Immutable domain event envelope used before persistence/outbox mapping."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from .identifiers import EntityId, TenantId
from .value_objects import ensure_aware


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    tenant_id: TenantId
    aggregate_type: str
    aggregate_id: EntityId
    occurred_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)
    version: int = 1

    def __post_init__(self) -> None:
        ensure_aware(self.occurred_at, "occurred_at")
        if not self.event_type.strip() or not self.aggregate_type.strip():
            raise ValueError("Event and aggregate types must not be blank")
        if self.version < 1:
            raise ValueError("Event version must be positive")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
