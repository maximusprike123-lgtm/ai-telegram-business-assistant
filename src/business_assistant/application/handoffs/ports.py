"""Tenant-scoped handoff persistence boundary."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import HandoffId, LeadId, TenantId

from .models import HandoffView


class HandoffStore(Protocol):
    async def schedule(self, tenant_id: TenantId) -> BusinessSchedule | None: ...
    async def active(self, identity: TelegramIdentity) -> HandoffView | None: ...
    async def create_or_get(
        self,
        identity: TelegramIdentity,
        *,
        reason_code: str,
        priority: str,
        summary: str,
        context: dict[str, Any],
        lead_id: LeadId | None,
        response_due_at: datetime,
        idempotency_key: str,
        now: datetime,
    ) -> HandoffView: ...
    async def list_open(self, tenant_id: TenantId, *, limit: int) -> Sequence[HandoffView]: ...
    async def transition(
        self,
        tenant_id: TenantId,
        handoff_id: HandoffId,
        *,
        action: str,
        actor_id: str,
        now: datetime,
    ) -> HandoffView: ...
