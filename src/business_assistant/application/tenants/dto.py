from dataclasses import dataclass

from ..scheduling.dto import BusinessDayDTO, BusinessStatusDTO, NextOpeningDTO


@dataclass(frozen=True, slots=True)
class TenantPublicProfileDTO:
    name: str
    description: str
    locale: str
    default_locale: str
    supported_locales: tuple[str, ...]
    timezone: str
    public_phone: str | None
    public_email: str | None
    website_url: str | None
    address: str | None
    service_area: str | None
    parking_guidance: str | None
    payment_methods: tuple[str, ...]
    warranty_policy: str | None
    appointment_policy: str | None
    business_hours: tuple[BusinessDayDTO, ...]
    status: BusinessStatusDTO
    next_opening: NextOpeningDTO
