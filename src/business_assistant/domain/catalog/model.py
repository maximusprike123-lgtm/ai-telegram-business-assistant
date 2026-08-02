from dataclasses import dataclass, field
from datetime import timedelta

from ..shared import CategoryId, Locale, PricePresentation, ServiceId, TenantId, ValidationError


def _validate_localized(values: dict[Locale, str], field_name: str) -> None:
    if not values or any(not value.strip() for value in values.values()):
        raise ValidationError(f"{field_name} requires non-blank localized content")


@dataclass(slots=True)
class ServiceCategory:
    id: CategoryId
    tenant_id: TenantId
    names: dict[Locale, str]
    sort_order: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        _validate_localized(self.names, "Category names")
        if self.sort_order < 0:
            raise ValidationError("Category sort order cannot be negative")


@dataclass(slots=True)
class Service:
    id: ServiceId
    tenant_id: TenantId
    category_id: CategoryId
    code: str
    names: dict[Locale, str]
    descriptions: dict[Locale, str]
    duration: timedelta
    price: PricePresentation
    cleanup_buffer: timedelta = timedelta()
    preparation_notes: dict[Locale, str] = field(default_factory=dict)
    eligibility_notes: dict[Locale, str] = field(default_factory=dict)
    active: bool = True
    bookable: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("Service code is required")
        _validate_localized(self.names, "Service names")
        _validate_localized(self.descriptions, "Service descriptions")
        if set(self.descriptions) - set(self.names):
            raise ValidationError("Service descriptions require a localized name")
        if self.duration <= timedelta(0):
            raise ValidationError("Service duration must be positive")
        if self.cleanup_buffer < timedelta(0):
            raise ValidationError("Cleanup buffer cannot be negative")
        if self.version < 1:
            raise ValidationError("Service version must be positive")

    @property
    def can_be_booked(self) -> bool:
        return self.active and self.bookable

    def archive(self) -> None:
        self.active = False
        self.bookable = False
