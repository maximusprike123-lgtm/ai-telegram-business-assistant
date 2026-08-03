from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["catalog.service_not_found"])
    message: str = Field(examples=["Service was not found"])
    correlation_id: str
    details: list[dict[str, str]] | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(examples=["43ec952c-c4f4-5387-9cb9-cbe42dd16ef5"])
    name: str = Field(examples=["Maintenance"])
    locale: str = Field(examples=["en"])
    sort_order: int


class PriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    mode: str = Field(examples=["starting_from"])
    currency: str | None = Field(examples=["RUB"])
    minimum_minor: int | None = Field(examples=[250000])
    maximum_minor: int | None
    display: str | None = Field(examples=["From RUB 2,500.00"])


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category_id: str
    code: str = Field(examples=["oil-change"])
    name: str = Field(examples=["Oil change"])
    description: str
    locale: str
    duration_seconds: int = Field(examples=[3600])
    duration_display: str = Field(examples=["1 hour"])
    price: PriceResponse
    preparation_notes: str | None
    eligibility_notes: str | None
    bookable: bool


class HoursIntervalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    start_local: str = Field(examples=["08:00"])
    end_local: str = Field(examples=["12:00"])


class BusinessDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    weekday: int
    day_label: str
    closed: bool
    intervals: tuple[HoursIntervalResponse, ...]
    source: str
    reason: str | None


class BusinessStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    open_now: bool = Field(examples=[True])
    evaluated_at: datetime
    local_date: date
    local_time: str
    timezone: str = Field(examples=["Europe/Moscow"])


class NextOpeningResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    open_now: bool
    next_opening_at: datetime | None
    next_opening_local: str | None
    timezone: str
    searched_days: int


class TenantProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    business_hours: tuple[BusinessDayResponse, ...]
    status: BusinessStatusResponse
    next_opening: NextOpeningResponse


class AvailabilitySlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    start_at: datetime
    end_at: datetime
    local_date: date
    local_time: str
    timezone: str
