"""Authorized tenant privacy and retention use cases."""

import re
from dataclasses import replace

from business_assistant.application.common.errors import PrivacyError
from business_assistant.application.common.ports import Clock
from business_assistant.application.common.security import Permission, Principal
from business_assistant.domain.shared import CustomerId

from .models import CLASSIFICATIONS, DataClassification, PrivacyResult, RetentionPolicy
from .ports import PrivacyStorePort

_SAFE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}")


class PrivacyApplication:
    def __init__(self, store: PrivacyStorePort, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def classifications(self, principal: Principal) -> tuple[DataClassification, ...]:
        principal.require(Permission.PRIVACY_READ)
        return CLASSIFICATIONS

    async def get_policy(self, principal: Principal) -> RetentionPolicy:
        principal.require(Permission.PRIVACY_READ)
        policy = await self._store.get_policy(principal.tenant_id)
        if policy is None:
            raise PrivacyError("Retention policy was not found", code="privacy.policy_not_found")
        return policy

    async def update_policy(
        self, principal: Principal, policy: RetentionPolicy, *, expected_version: int
    ) -> RetentionPolicy:
        principal.require(Permission.PRIVACY_POLICY_WRITE)
        if policy.tenant_id != principal.tenant_id:
            raise PrivacyError("Retention policy tenant does not match the authenticated tenant")
        return await self._store.update_policy(
            replace(policy, version=expected_version + 1),
            expected_version=expected_version,
            actor_id=principal.subject,
            at=self._clock.now(),
        )

    async def anonymize_customer(
        self,
        principal: Principal,
        customer_id: CustomerId,
        *,
        confirmed: bool,
        idempotency_key: str,
        reason_code: str,
    ) -> PrivacyResult:
        principal.require(Permission.PRIVACY_EXECUTE)
        if not confirmed:
            raise PrivacyError("Customer anonymization requires explicit confirmation")
        _validate_code(idempotency_key, "idempotency key")
        _validate_code(reason_code, "reason code")
        return await self._store.anonymize_customer(
            principal.tenant_id,
            customer_id,
            idempotency_key=idempotency_key,
            reason_code=reason_code,
            actor_id=principal.subject,
            at=self._clock.now(),
        )

    async def preview_retention(self, principal: Principal) -> PrivacyResult:
        principal.require(Permission.PRIVACY_READ)
        policy = await self.get_policy(principal)
        return await self._store.run_retention(
            principal.tenant_id,
            policy,
            dry_run=True,
            idempotency_key=None,
            actor_id=principal.subject,
            at=self._clock.now(),
        )

    async def execute_retention(
        self, principal: Principal, *, confirmed: bool, idempotency_key: str
    ) -> PrivacyResult:
        principal.require(Permission.PRIVACY_EXECUTE)
        if not confirmed:
            raise PrivacyError("Retention execution requires explicit confirmation")
        _validate_code(idempotency_key, "idempotency key")
        policy = await self.get_policy(principal)
        return await self._store.run_retention(
            principal.tenant_id,
            policy,
            dry_run=False,
            idempotency_key=idempotency_key,
            actor_id=principal.subject,
            at=self._clock.now(),
        )


def _validate_code(value: str, label: str) -> None:
    if _SAFE_CODE.fullmatch(value) is None:
        raise PrivacyError(f"Privacy {label} is invalid")
