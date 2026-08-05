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
    LEAD_READ = "lead:read"
    QUALIFICATION_SCHEMA_READ = "qualification_schema:read"
    QUALIFICATION_SCHEMA_WRITE = "qualification_schema:write"
    HANDOFF_READ = "handoff:read"
    HANDOFF_WRITE = "handoff:write"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    PRIVACY_READ = "privacy:read"
    PRIVACY_POLICY_WRITE = "privacy_policy:write"
    PRIVACY_EXECUTE = "privacy:execute"
    NOTIFICATION_READ = "notification:read"
    NOTIFICATION_WRITE = "notification:write"
    WORKER_MONITOR_READ = "worker_monitor:read"


_READ_PERMISSIONS = frozenset(
    {
        Permission.PUBLIC_PROFILE_READ,
        Permission.CATALOG_READ,
        Permission.SCHEDULE_READ,
        Permission.BOOKING_READ,
        Permission.LEAD_READ,
        Permission.QUALIFICATION_SCHEMA_READ,
        Permission.HANDOFF_READ,
        Permission.KNOWLEDGE_READ,
    }
)
_WRITE_PERMISSIONS = frozenset(
    {
        Permission.QUALIFICATION_SCHEMA_WRITE,
        Permission.HANDOFF_WRITE,
        Permission.KNOWLEDGE_WRITE,
    }
)
_PRIVACY_READ_PERMISSIONS = frozenset({Permission.PRIVACY_READ})
_PRIVACY_OWNER_PERMISSIONS = frozenset(
    {Permission.PRIVACY_POLICY_WRITE, Permission.PRIVACY_EXECUTE}
)
_OPERATIONS_PERMISSIONS = frozenset(
    {Permission.NOTIFICATION_READ, Permission.NOTIFICATION_WRITE, Permission.WORKER_MONITOR_READ}
)
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _READ_PERMISSIONS
    | _WRITE_PERMISSIONS
    | _PRIVACY_READ_PERMISSIONS
    | _PRIVACY_OWNER_PERMISSIONS
    | _OPERATIONS_PERMISSIONS,
    Role.MANAGER: (
        _READ_PERMISSIONS | _WRITE_PERMISSIONS | _PRIVACY_READ_PERMISSIONS | _OPERATIONS_PERMISSIONS
    ),
    Role.AGENT: _READ_PERMISSIONS | {Permission.HANDOFF_WRITE},
    Role.VIEWER: _READ_PERMISSIONS,
    Role.KNOWLEDGE_EDITOR: frozenset({Permission.KNOWLEDGE_READ, Permission.KNOWLEDGE_WRITE}),
}


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: TenantId
    role: Role

    def require(self, permission: Permission) -> None:
        if permission not in _ROLE_PERMISSIONS[self.role]:
            raise AuthorizationError()
