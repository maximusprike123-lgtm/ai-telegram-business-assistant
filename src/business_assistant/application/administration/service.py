"""Authorized tenant control-plane orchestration."""

from datetime import datetime
from uuid import UUID

from business_assistant.application.common.security import Permission, Principal, Role
from business_assistant.domain.shared import Locale
from business_assistant.domain.tenants import Tenant, TenantStatus

from .models import (
    Capability,
    CredentialIssue,
    CredentialView,
    EntitlementView,
    MemberView,
    ProvisioningResult,
    ProvisionTenant,
    TenantView,
)
from .ports import CredentialSecretPort, TenantAdministrationStore


class TenantAdministration:
    def __init__(self, store: TenantAdministrationStore, secrets: CredentialSecretPort) -> None:
        self._store = store
        self._secrets = secrets

    async def provision(self, request: ProvisionTenant) -> ProvisioningResult:
        _validate_text(request.owner_subject, 200, "Owner subject")
        _validate_text(request.credential_name, 100, "Credential name")
        _validate_text(request.idempotency_key, 200, "Idempotency key")
        Tenant(
            request.tenant_id,
            request.slug,
            request.name,
            request.timezone,
            request.default_locale,
            frozenset({request.default_locale}),
            TenantStatus.SUSPENDED,
        )
        return await self._store.provision(request, self._secrets.issue())

    async def get_tenant(self, principal: Principal) -> TenantView:
        principal.require(Permission.TENANT_ADMIN_READ)
        tenant = await self._store.tenant(principal.tenant_id)
        if tenant is None:
            raise ValueError("Tenant was not found")
        return tenant

    async def update_tenant(
        self,
        principal: Principal,
        *,
        name: str,
        timezone: str,
        default_locale: Locale,
        expected_version: int,
    ) -> TenantView:
        principal.require(Permission.TENANT_PROFILE_WRITE)
        _validate_text(name, 200, "Tenant name")
        return await self._store.update_tenant(
            principal.tenant_id,
            name=name,
            timezone=timezone,
            default_locale=default_locale,
            expected_version=expected_version,
            actor=principal.subject,
        )

    async def transition(self, principal: Principal, target: TenantStatus) -> TenantView:
        principal.require(Permission.TENANT_LIFECYCLE_WRITE)
        return await self._store.transition_tenant(
            principal.tenant_id, target, actor=principal.subject
        )

    async def members(self, principal: Principal) -> tuple[MemberView, ...]:
        principal.require(Permission.TENANT_ADMIN_READ)
        return await self._store.members(principal.tenant_id)

    async def upsert_member(self, principal: Principal, *, subject: str, role: Role) -> MemberView:
        principal.require(Permission.TENANT_MEMBER_WRITE)
        _validate_text(subject, 200, "Member subject")
        return await self._store.upsert_member(
            principal.tenant_id, subject=subject, role=role, actor=principal.subject
        )

    async def revoke_member(self, principal: Principal, member_id: UUID) -> MemberView:
        principal.require(Permission.TENANT_MEMBER_WRITE)
        return await self._store.revoke_member(
            principal.tenant_id, member_id, actor=principal.subject
        )

    async def credentials(self, principal: Principal) -> tuple[CredentialView, ...]:
        principal.require(Permission.TENANT_ADMIN_READ)
        return await self._store.credentials(principal.tenant_id)

    async def create_credential(
        self,
        principal: Principal,
        *,
        member_id: UUID,
        name: str,
        expires_at: datetime | None,
    ) -> CredentialIssue:
        principal.require(Permission.TENANT_CREDENTIAL_WRITE)
        _validate_text(name, 100, "Credential name")
        material = self._secrets.issue()
        view = await self._store.create_credential(
            principal.tenant_id,
            member_id=member_id,
            name=name,
            expires_at=expires_at,
            material=material,
            actor=principal.subject,
        )
        return CredentialIssue(view, material.plaintext)

    async def rotate_credential(
        self,
        principal: Principal,
        credential_id: UUID,
        *,
        expires_at: datetime | None,
    ) -> CredentialIssue:
        principal.require(Permission.TENANT_CREDENTIAL_WRITE)
        material = self._secrets.issue()
        view = await self._store.rotate_credential(
            principal.tenant_id,
            credential_id,
            expires_at=expires_at,
            material=material,
            actor=principal.subject,
        )
        return CredentialIssue(view, material.plaintext)

    async def revoke_credential(self, principal: Principal, credential_id: UUID) -> CredentialIssue:
        principal.require(Permission.TENANT_CREDENTIAL_WRITE)
        view = await self._store.revoke_credential(
            principal.tenant_id, credential_id, actor=principal.subject
        )
        return CredentialIssue(view, None)

    async def entitlements(self, principal: Principal) -> tuple[EntitlementView, ...]:
        principal.require(Permission.TENANT_ADMIN_READ)
        return await self._store.entitlements(principal.tenant_id)

    async def set_entitlement(
        self,
        principal: Principal,
        capability: Capability,
        *,
        enabled: bool,
        expected_version: int,
    ) -> EntitlementView:
        principal.require(Permission.TENANT_ENTITLEMENT_WRITE)
        return await self._store.set_entitlement(
            principal.tenant_id,
            capability,
            enabled=enabled,
            expected_version=expected_version,
            actor=principal.subject,
        )


def _validate_text(value: str, maximum: int, label: str) -> None:
    if not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} is invalid")
