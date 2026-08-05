from datetime import date, datetime
from decimal import Decimal
from typing import Literal

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


class QualificationValidationSchema(BaseModel):
    min_length: int | None = Field(default=None, ge=0, le=4000)
    max_length: int | None = Field(default=None, ge=1, le=4000)
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    options: tuple[str, ...] = Field(default=(), max_length=50)
    pattern: str | None = Field(default=None, max_length=500)


class QualificationScoreRuleSchema(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    operator: Literal["equals", "contains", "gte", "lte"]
    expected: str | int | Decimal | bool
    points: int = Field(ge=-100, le=100)


class QualificationHandoffRuleSchema(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    operator: Literal["equals", "contains", "gte", "lte"]
    expected: str | int | Decimal | bool
    reason_code: str = Field(min_length=1, max_length=100)
    priority: Literal["low", "normal", "high", "urgent"]


class QualificationFieldSchema(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=100)
    label: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=1000)
    field_type: Literal[
        "short_text",
        "long_text",
        "single_choice",
        "multi_choice",
        "phone",
        "email",
        "integer",
        "decimal",
        "boolean",
        "date",
    ]
    validation: QualificationValidationSchema
    required: bool
    order: int = Field(ge=0, le=100)
    sensitivity: Literal["public", "personal", "sensitive"]
    score_rules: tuple[QualificationScoreRuleSchema, ...] = Field(default=(), max_length=50)
    handoff_triggers: tuple[QualificationHandoffRuleSchema, ...] = Field(default=(), max_length=50)


class QualificationGradeSchema(BaseModel):
    minimum_score: int = Field(ge=0, le=100)
    grade: str = Field(min_length=1, max_length=20)


class QualificationSchemaCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    consent_version: str = Field(min_length=1, max_length=50)
    consent_purpose: str = Field(min_length=1, max_length=500)
    fields: tuple[QualificationFieldSchema, ...] = Field(min_length=1, max_length=50)
    grade_bands: tuple[QualificationGradeSchema, ...] = Field(min_length=1, max_length=20)
    session_ttl_minutes: int = Field(ge=5, le=10080)
    handoff_response_minutes: int = Field(ge=1, le=10080)
    active: bool = True


class QualificationSchemaResponse(QualificationSchemaCreate):
    id: str
    published: bool


class HandoffResponse(BaseModel):
    id: str
    conversation_id: str
    lead_id: str | None
    reason_code: str
    priority: str
    status: str
    summary: str
    context: dict[str, object]
    response_due_at: datetime
    assignee_id: str | None


class HandoffActionRequest(BaseModel):
    action: Literal["claim", "resolve", "reopen", "return_to_bot"]


class MarkdownKnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    markdown: str = Field(min_length=1, max_length=10_485_760)
    locale: Literal["en"] = "en"


class FAQKnowledgeCreate(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10_000)
    aliases: tuple[str, ...] = Field(default=(), max_length=20)
    priority: int = Field(default=0, ge=0, le=100)
    locale: Literal["en"] = "en"


class KnowledgeDocumentResponse(BaseModel):
    id: str
    title: str
    locale: str
    source_type: str
    checksum: str
    version: int
    status: str
    published_at: datetime | None
    chunk_count: int


class KnowledgeAnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    locale: Literal["en"] = "en"


class KnowledgeCitationResponse(BaseModel):
    document_id: str
    document_version: int
    chunk_id: str
    title: str
    section: str | None
    score: float
    content_checksum: str


class KnowledgeAnswerResponse(BaseModel):
    answered: bool
    text: str
    citations: tuple[KnowledgeCitationResponse, ...]
    fallback_reason: str | None


class DataClassificationResponse(BaseModel):
    data_class: str
    purpose: str
    sensitivity: str
    retention_action: str


class RetentionPolicyUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    operational_metadata_days: int = Field(ge=1, le=3650)
    message_content_days: int = Field(ge=1, le=3650)
    customer_contact_days: int = Field(ge=1, le=3650)
    workflow_records_days: int = Field(ge=1, le=3650)
    knowledge_archive_days: int = Field(ge=1, le=3650)
    ai_telemetry_days: int = Field(ge=1, le=3650)


class RetentionPolicyResponse(BaseModel):
    version: int
    operational_metadata_days: int
    message_content_days: int
    customer_contact_days: int
    workflow_records_days: int
    knowledge_archive_days: int
    ai_telemetry_days: int


class PrivacyExecutionRequest(BaseModel):
    confirmed: bool
    idempotency_key: str = Field(min_length=1, max_length=200)


class CustomerAnonymizationRequest(PrivacyExecutionRequest):
    reason_code: str = Field(min_length=1, max_length=100)


class PrivacyResultResponse(BaseModel):
    action_id: str | None
    action: str
    dry_run: bool
    policy_version: int
    counts: dict[str, int]
    idempotent_replay: bool
