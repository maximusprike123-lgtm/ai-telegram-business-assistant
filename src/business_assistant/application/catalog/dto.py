from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceCategoryDTO:
    id: str
    name: str
    locale: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class PublicPriceDTO:
    mode: str
    currency: str | None
    minimum_minor: int | None
    maximum_minor: int | None
    display: str | None


@dataclass(frozen=True, slots=True)
class ServiceDTO:
    id: str
    category_id: str
    code: str
    name: str
    description: str
    locale: str
    duration_seconds: int
    duration_display: str
    price: PublicPriceDTO
    preparation_notes: str | None
    eligibility_notes: str | None
    bookable: bool
