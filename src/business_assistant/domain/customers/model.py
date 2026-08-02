from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..shared import CustomerId, Locale, PhoneNumber, TenantId, ValidationError, ensure_aware


class CustomerStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    ANONYMIZED = "anonymized"


@dataclass(slots=True)
class Customer:
    id: CustomerId
    tenant_id: TenantId
    locale: Locale
    display_name: str | None = None
    phone: PhoneNumber | None = None
    email: str | None = None
    privacy_notice_version: str | None = None
    privacy_accepted_at: datetime | None = None
    contact_consent_at: datetime | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.display_name is not None and not self.display_name.strip():
            raise ValidationError("Display name cannot be blank")
        if self.email is not None and ("@" not in self.email or len(self.email) > 254):
            raise ValidationError("Email address is invalid")
        for field_name, value in (
            ("privacy_accepted_at", self.privacy_accepted_at),
            ("contact_consent_at", self.contact_consent_at),
        ):
            if value is not None:
                ensure_aware(value, field_name)
        if (self.privacy_notice_version is None) != (self.privacy_accepted_at is None):
            raise ValidationError("Privacy acceptance requires both version and timestamp")

    def accept_privacy_notice(self, version: str, accepted_at: datetime) -> None:
        ensure_aware(accepted_at, "accepted_at")
        if not version.strip():
            raise ValidationError("Privacy notice version is required")
        self.privacy_notice_version = version
        self.privacy_accepted_at = accepted_at

    def grant_contact_consent(self, granted_at: datetime) -> None:
        self.contact_consent_at = ensure_aware(granted_at, "granted_at")

    def update_phone(self, phone: PhoneNumber) -> None:
        if self.contact_consent_at is None:
            raise ValidationError("Contact consent is required before storing a phone number")
        self.phone = phone
