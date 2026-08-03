"""Framework-independent authenticated tenant context and RBAC policy."""

from dataclasses import dataclass
from enum import StrEnum

from business_assistant.domain.shared import TenantId

from .errors import AuthorizationError


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    AGENT = "agent"
    KNOWLEDGE_EDITOR = "knowledge_editor"
    VIEWER = "viewer"


class Permission(StrEnum):
    PUBLIC_PROFILE_READ = "public_profile:read"
    CATALOG_READ = "catalog:read"
    SCHEDULE_READ = "schedule:read"
    BOOKING_READ = "booking:read"


_READ_PERMISSIONS = frozenset(Permission)
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _READ_PERMISSIONS,
    Role.MANAGER: _READ_PERMISSIONS,
    Role.AGENT: _READ_PERMISSIONS,
    Role.VIEWER: _READ_PERMISSIONS,
    Role.KNOWLEDGE_EDITOR: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: TenantId
    role: Role

    def require(self, permission: Permission) -> None:
        if permission not in _ROLE_PERMISSIONS[self.role]:
            raise AuthorizationError()
