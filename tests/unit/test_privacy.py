from dataclasses import replace
from datetime import UTC, datetime

import pytest

from business_assistant.application.common.errors import AuthorizationError, PrivacyError
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.privacy import (
    PrivacyApplication,
    PrivacyResult,
    RetentionPolicy,
)
from business_assistant.domain.shared import CustomerId, TenantId


class Clock:
    def now(self):
        return datetime(2026, 8, 5, 12, tzinfo=UTC)


class Store:
    def __init__(self, policy: RetentionPolicy) -> None:
        self.policy = policy
        self.calls = []

    async def get_policy(self, tenant_id):
        return self.policy if tenant_id == self.policy.tenant_id else None

    async def update_policy(self, policy, **kwargs):
        self.calls.append(("update", policy, kwargs))
        self.policy = policy
        return policy

    async def anonymize_customer(self, tenant_id, customer_id, **kwargs):
        self.calls.append(("anonymize", tenant_id, customer_id, kwargs))
        return PrivacyResult("action", "customer_anonymization", False, 1, {"customers": 1})

    async def run_retention(self, tenant_id, policy, **kwargs):
        self.calls.append(("retention", tenant_id, policy, kwargs))
        return PrivacyResult(
            None if kwargs["dry_run"] else "action",
            "retention_preview" if kwargs["dry_run"] else "retention_execution",
            kwargs["dry_run"],
            policy.version,
            {"messages_deleted": 2},
        )


def fixture(role: Role = Role.OWNER):
    tenant_id = TenantId.new()
    policy = RetentionPolicy(tenant_id, 1, 30, 90, 365, 730, 365, 90)
    store = Store(policy)
    principal = Principal("operator", tenant_id, role)
    return PrivacyApplication(store, Clock()), store, principal, policy


@pytest.mark.asyncio
async def test_classification_policy_and_optimistic_update_are_authorized() -> None:
    application, store, owner, policy = fixture()
    classifications = application.classifications(owner)
    assert {item.data_class.value for item in classifications} == {
        "operational_metadata",
        "message_content",
        "customer_contact",
        "workflow_records",
        "knowledge",
        "audit_security",
        "ai_telemetry",
    }
    assert (await application.get_policy(owner)) == policy
    updated = await application.update_policy(
        owner, replace(policy, version=2, message_content_days=60), expected_version=1
    )
    assert updated.version == 2
    assert store.calls[-1][2]["expected_version"] == 1


@pytest.mark.asyncio
async def test_destructive_operations_require_owner_confirmation_and_safe_keys() -> None:
    application, store, owner, _ = fixture()
    customer_id = CustomerId.new()
    with pytest.raises(PrivacyError, match="confirmation"):
        await application.anonymize_customer(
            owner,
            customer_id,
            confirmed=False,
            idempotency_key="request-1",
            reason_code="customer_request",
        )
    with pytest.raises(PrivacyError, match="invalid"):
        await application.execute_retention(owner, confirmed=True, idempotency_key="unsafe key")
    result = await application.anonymize_customer(
        owner,
        customer_id,
        confirmed=True,
        idempotency_key="request-1",
        reason_code="customer_request",
    )
    assert result.counts["customers"] == 1
    assert store.calls[-1][0] == "anonymize"


@pytest.mark.asyncio
async def test_manager_can_preview_but_only_owner_can_mutate() -> None:
    application, _, manager, policy = fixture(Role.MANAGER)
    assert (await application.preview_retention(manager)).dry_run
    with pytest.raises(AuthorizationError):
        await application.update_policy(manager, replace(policy, version=2), expected_version=1)
    with pytest.raises(AuthorizationError):
        await application.execute_retention(manager, confirmed=True, idempotency_key="retention-1")


@pytest.mark.asyncio
async def test_policy_rejects_unbounded_periods_and_cross_tenant_update() -> None:
    with pytest.raises(ValueError, match="between"):
        RetentionPolicy(TenantId.new(), 1, 0, 90, 365, 730, 365, 90)
    application, _, owner, policy = fixture()
    with pytest.raises(PrivacyError, match="tenant"):
        await application.update_policy(
            owner,
            replace(policy, tenant_id=TenantId.new(), version=2),
            expected_version=1,
        )
