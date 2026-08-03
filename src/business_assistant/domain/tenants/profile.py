"""Customer-safe, versioned tenant business configuration."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..shared import Locale, ScheduleId, TenantId, ValidationError


def _validate_optional_localized(values: dict[Locale, str], field_name: str) -> None:
    if any(not value.strip() for value in values.values()):
        raise ValidationError(f"{field_name} cannot contain blank localized content")


@dataclass(slots=True)
class TenantPublicProfile:
    tenant_id: TenantId
    schedule_id: ScheduleId
    descriptions: dict[Locale, str]
    public_phone: str | None = None
    public_email: str | None = None
    website_url: str | None = None
    addresses: dict[Locale, str] = field(default_factory=dict)
    service_areas: dict[Locale, str] = field(default_factory=dict)
    parking_guidance: dict[Locale, str] = field(default_factory=dict)
    payment_methods: tuple[str, ...] = ()
    warranty_policy: dict[Locale, str] = field(default_factory=dict)
    appointment_policy: dict[Locale, str] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        for values, name in (
            (self.descriptions, "Descriptions"),
            (self.addresses, "Addresses"),
            (self.service_areas, "Service areas"),
            (self.parking_guidance, "Parking guidance"),
            (self.warranty_policy, "Warranty policy"),
            (self.appointment_policy, "Appointment policy"),
        ):
            _validate_optional_localized(values, name)
        if not self.descriptions:
            raise ValidationError("Public profile requires a localized description")
        if self.public_phone is not None and (
            not self.public_phone.strip() or len(self.public_phone) > 32
        ):
            raise ValidationError("Public phone number is invalid")
        if self.public_email is not None and (
            not self.public_email.strip()
            or "@" not in self.public_email
            or len(self.public_email) > 254
        ):
            raise ValidationError("Public email address is invalid")
        if self.website_url is not None:
            parsed = urlsplit(self.website_url)
            if (
                len(self.website_url) > 500
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
            ):
                raise ValidationError("Public website URL is invalid")
        if any(not item.strip() for item in self.payment_methods):
            raise ValidationError("Payment methods cannot contain blank values")
        if self.version < 1:
            raise ValidationError("Public profile version must be positive")
