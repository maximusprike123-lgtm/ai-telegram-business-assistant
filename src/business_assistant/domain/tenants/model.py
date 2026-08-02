from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..shared import Locale, TenantId, ValidationError


class TenantStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(slots=True)
class Tenant:
    id: TenantId
    slug: str
    name: str
    timezone: str
    default_locale: Locale
    supported_locales: frozenset[Locale]
    status: TenantStatus = TenantStatus.ACTIVE
    settings_version: int = 1

    def __post_init__(self) -> None:
        if not self.slug.strip() or not self.name.strip():
            raise ValidationError("Tenant slug and name are required")
        if not self.slug.isascii() or any(
            c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in self.slug
        ):
            raise ValidationError(
                "Tenant slug must use lowercase ASCII letters, digits, or hyphens"
            )
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError("Tenant timezone must be a valid IANA timezone") from exc
        if not self.supported_locales or self.default_locale not in self.supported_locales:
            raise ValidationError("Default locale must be in the supported locale allowlist")
        if self.settings_version < 1:
            raise ValidationError("Tenant settings version must be positive")

    @property
    def can_process_new_work(self) -> bool:
        return self.status is TenantStatus.ACTIVE

    def deactivate(self) -> None:
        self.status = TenantStatus.INACTIVE

    def activate(self) -> None:
        self.status = TenantStatus.ACTIVE
