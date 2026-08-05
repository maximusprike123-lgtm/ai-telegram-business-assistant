"""Tenant control-plane values with no adapter dependencies."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from business_assistant.application.common.errors import ApplicationError
from business_assistant.application.common.security import Role
from business_assistant.domain.shared import Locale, TenantId
from business_assistant.domain.tenants import TenantStatus


class Capability(StrEnum):
    TELEGRAM = "telegram"
    BOOKING = "booking"
    QUALIFICATION = "qualification"
    AI_ROUTING = "ai_routing"
    KNOWLEDGE_ANSWERS = "knowledge_answers"
    BACKGROUND_NOTIFICATIONS = "background_notifications"
    AUTOMATIC_RETENTION = "automatic_retention"


class AdministrationError(ApplicationError):
    def __init__(
        self,
        message: str = "Tenant administration operation is invalid",
        *,
        code: str = "administration.invalid",
    ) -> None:
        super().__init__(code, message)


@dataclass(frozen=True, slots=True)
class TenantView:
    id: TenantId
    slug: str
    name: str
    timezone: str
    default_locale: Locale
    supported_locales: frozenset[Locale]
    status: TenantStatus
    settings_version: int


@dataclass(frozen=True, slots=True)
class MemberView:
    id: UUID
    tenant_id: TenantId
    subject: str
    role: Role
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CredentialView:
    id: UUID
    tenant_id: TenantId
    member_id: UUID
    name: str
    key_prefix: str
    role: Role
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CredentialIssue:
    credential: CredentialView
    secret: str | None


@dataclass(frozen=True, slots=True)
class CredentialMaterial:
    prefix: str
    secret_hash: str
    plaintext: str


@dataclass(frozen=True, slots=True)
class EntitlementView:
    capability: Capability
    enabled: bool
    version: int


@dataclass(frozen=True, slots=True)
class ProvisionTenant:
    tenant_id: TenantId
    slug: str
    name: str
    timezone: str
    default_locale: Locale
    owner_subject: str
    credential_name: str
    idempotency_key: str
    entitlements: frozenset[Capability]


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    tenant: TenantView
    owner: MemberView
    credential: CredentialIssue
    created: bool
