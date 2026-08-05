"""Inward-facing background processing ports."""

from datetime import datetime
from typing import Protocol

from business_assistant.domain.shared import TenantId

from .models import DeliveryClaim, NotificationSubscription, WorkerHealth


class BackgroundStorePort(Protocol):
    async def save_subscription(
        self, subscription: NotificationSubscription
    ) -> NotificationSubscription: ...

    async def list_subscriptions(
        self, tenant_id: TenantId
    ) -> tuple[NotificationSubscription, ...]: ...

    async def dispatch_outbox(
        self, *, now: datetime, limit: int, lease_seconds: int, max_attempts: int
    ) -> tuple[int, int, int]: ...

    async def claim_notifications(
        self, *, now: datetime, limit: int, lease_seconds: int
    ) -> tuple[DeliveryClaim, ...]: ...

    async def mark_delivered(self, claim: DeliveryClaim, *, at: datetime) -> None: ...

    async def retry_delivery(
        self, claim: DeliveryClaim, *, at: datetime, error_code: str
    ) -> None: ...

    async def dead_letter(self, claim: DeliveryClaim, *, at: datetime, error_code: str) -> None: ...

    async def health(self, tenant_id: TenantId) -> WorkerHealth: ...


class NotificationGatewayPort(Protocol):
    async def send(self, claim: DeliveryClaim, *, text: str) -> None: ...
