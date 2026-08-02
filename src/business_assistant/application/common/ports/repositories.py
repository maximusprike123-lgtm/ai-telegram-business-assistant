"""Tenant-scoped persistence boundary."""

from collections.abc import Sequence
from typing import Protocol, TypeVar

from business_assistant.domain.shared import EntityId, TenantId

EntityT = TypeVar("EntityT")
IdentifierT = TypeVar("IdentifierT", bound=EntityId, contravariant=True)


class Repository(Protocol[EntityT, IdentifierT]):
    async def get(self, tenant_id: TenantId, entity_id: IdentifierT) -> EntityT | None:
        """Fetch only within the explicit tenant scope."""
        ...

    async def add(self, tenant_id: TenantId, entity: EntityT) -> None:
        """Stage a tenant-owned aggregate for persistence."""
        ...

    async def list_page(
        self,
        tenant_id: TenantId,
        *,
        cursor: str | None,
        limit: int,
    ) -> Sequence[EntityT]:
        """Return one bounded, tenant-scoped page."""
        ...
