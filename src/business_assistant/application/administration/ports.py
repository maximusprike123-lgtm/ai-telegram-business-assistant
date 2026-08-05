"""Ports for tenant administration, credentials, and access policy."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import Locale, TenantId
from business_assistant.domain.tenants import TenantStatus

from .models import (
    BusinessProfileView,
    Capability,
    CredentialMaterial,
    CredentialView,
    EntitlementView,
    MemberView,
    ProvisioningResult,
    ProvisionTenant,
    TenantView,
)


class CredentialSecretPort(Protocol):
    def issue(self) -> CredentialMaterial: ...


class TenantAdministrationStore(Protocol):
    async def provision(
        self, request: ProvisionTenant, material: CredentialMaterial
    ) -> ProvisioningResult: ...

    async def tenant(self, tenant_id: TenantId) -> TenantView | None: ...
    async def business_profile(self, tenant_id: TenantId) -> BusinessProfileView: ...
    async def update_business_profile(
        self,
        tenant_id: TenantId,
        profile: BusinessProfileView,
        *,
        expected_version: int,
        actor: str,
    ) -> BusinessProfileView: ...
    async def update_tenant(
        self,
        tenant_id: TenantId,
        *,
        name: str,
        timezone: str,
        default_locale: Locale,
        expected_version: int,
        actor: str,
    ) -> TenantView: ...
    async def transition_tenant(
        self, tenant_id: TenantId, target: TenantStatus, *, actor: str
    ) -> TenantView: ...
    async def members(self, tenant_id: TenantId) -> tuple[MemberView, ...]: ...
    async def upsert_member(
        self, tenant_id: TenantId, *, subject: str, role: Role, actor: str
    ) -> MemberView: ...
    async def revoke_member(
        self, tenant_id: TenantId, member_id: UUID, *, actor: str
    ) -> MemberView: ...
    async def credentials(self, tenant_id: TenantId) -> tuple[CredentialView, ...]: ...
    async def create_credential(
        self,
        tenant_id: TenantId,
        *,
        member_id: UUID,
        name: str,
        expires_at: datetime | None,
        material: CredentialMaterial,
        actor: str,
    ) -> CredentialView: ...
    async def rotate_credential(
        self,
        tenant_id: TenantId,
        credential_id: UUID,
        *,
        expires_at: datetime | None,
        material: CredentialMaterial,
        actor: str,
    ) -> CredentialView: ...
    async def revoke_credential(
        self, tenant_id: TenantId, credential_id: UUID, *, actor: str
    ) -> CredentialView: ...
    async def entitlements(self, tenant_id: TenantId) -> tuple[EntitlementView, ...]: ...
    async def set_entitlement(
        self,
        tenant_id: TenantId,
        capability: Capability,
        *,
        enabled: bool,
        expected_version: int,
        actor: str,
    ) -> EntitlementView: ...


class TenantAccessPolicy(Protocol):
    async def require_active(
        self, tenant_id: TenantId, capability: Capability | None = None
    ) -> None: ...


class ApiKeyAuthenticator(Protocol):
    async def authenticate(self, provided_key: str | None) -> Principal: ...
