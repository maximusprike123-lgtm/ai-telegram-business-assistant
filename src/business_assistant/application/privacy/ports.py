"""Inward-facing persistence port for privacy workflows."""

from datetime import datetime
from typing import Protocol

from business_assistant.domain.shared import CustomerId, TenantId

from .models import PrivacyResult, RetentionPolicy


class PrivacyStorePort(Protocol):
    async def get_policy(self, tenant_id: TenantId) -> RetentionPolicy | None: ...

    async def update_policy(
        self, policy: RetentionPolicy, *, expected_version: int, actor_id: str, at: datetime
    ) -> RetentionPolicy: ...

    async def anonymize_customer(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        *,
        idempotency_key: str,
        reason_code: str,
        actor_id: str,
        at: datetime,
    ) -> PrivacyResult: ...

    async def run_retention(
        self,
        tenant_id: TenantId,
        policy: RetentionPolicy,
        *,
        dry_run: bool,
        idempotency_key: str | None,
        actor_id: str,
        at: datetime,
    ) -> PrivacyResult: ...
