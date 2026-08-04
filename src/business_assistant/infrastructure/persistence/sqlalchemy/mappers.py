"""Bidirectional translations between domain aggregates and persistence rows."""

from datetime import timedelta

from business_assistant.domain.bookings import Booking, BookingStatus
from business_assistant.domain.catalog import Service, ServiceCategory
from business_assistant.domain.conversations import Conversation, ConversationStatus
from business_assistant.domain.customers import Customer, CustomerStatus
from business_assistant.domain.handoffs import HandoffCase, HandoffPriority, HandoffStatus
from business_assistant.domain.knowledge import KnowledgeDocument, KnowledgeStatus
from business_assistant.domain.leads import Lead, LeadPriority, LeadStatus
from business_assistant.domain.scheduling import (
    BusinessSchedule,
    IntervalType,
    ScheduleInterval,
    ScheduleOverride,
)
from business_assistant.domain.shared import (
    BookingId,
    CategoryId,
    ConversationId,
    CustomerId,
    DocumentId,
    HandoffId,
    IdempotencyKey,
    LeadId,
    Locale,
    Money,
    PhoneNumber,
    PriceMode,
    PricePresentation,
    ScheduleId,
    ServiceId,
    TenantId,
    TimeRange,
)
from business_assistant.domain.tenants import Tenant, TenantPublicProfile, TenantStatus

from .models import (
    BookingRow,
    BusinessScheduleRow,
    ConversationRow,
    CustomerRow,
    HandoffCaseRow,
    KnowledgeDocumentRow,
    LeadRow,
    ScheduleIntervalRow,
    ScheduleOverrideRow,
    ServiceCategoryRow,
    ServiceRow,
    TenantPublicProfileRow,
    TenantRow,
)


def tenant_to_row(entity: Tenant) -> TenantRow:
    return TenantRow(
        id=entity.id.value,
        slug=entity.slug,
        name=entity.name,
        timezone=entity.timezone,
        default_locale=entity.default_locale.value,
        supported_locales=sorted(locale.value for locale in entity.supported_locales),
        status=entity.status.value,
        settings_version=entity.settings_version,
    )


def tenant_from_row(row: TenantRow) -> Tenant:
    return Tenant(
        id=TenantId(row.id),
        slug=row.slug,
        name=row.name,
        timezone=row.timezone,
        default_locale=Locale(row.default_locale),
        supported_locales=frozenset(Locale(item) for item in row.supported_locales),
        status=TenantStatus(row.status),
        settings_version=row.settings_version,
    )


def _localized_to_json(values: dict[Locale, str]) -> dict[str, str]:
    return {key.value: value for key, value in values.items()}


def _localized_from_json(values: dict[str, str]) -> dict[Locale, str]:
    return {Locale(key): value for key, value in values.items()}


def public_profile_to_row(entity: TenantPublicProfile) -> TenantPublicProfileRow:
    return TenantPublicProfileRow(
        tenant_id=entity.tenant_id.value,
        schedule_id=entity.schedule_id.value,
        descriptions=_localized_to_json(entity.descriptions),
        public_phone=entity.public_phone,
        public_email=entity.public_email,
        website_url=entity.website_url,
        addresses=_localized_to_json(entity.addresses),
        service_areas=_localized_to_json(entity.service_areas),
        parking_guidance=_localized_to_json(entity.parking_guidance),
        payment_methods=list(entity.payment_methods),
        warranty_policy=_localized_to_json(entity.warranty_policy),
        appointment_policy=_localized_to_json(entity.appointment_policy),
        version=entity.version,
    )


def public_profile_from_row(row: TenantPublicProfileRow) -> TenantPublicProfile:
    return TenantPublicProfile(
        tenant_id=TenantId(row.tenant_id),
        schedule_id=ScheduleId(row.schedule_id),
        descriptions=_localized_from_json(row.descriptions),
        public_phone=row.public_phone,
        public_email=row.public_email,
        website_url=row.website_url,
        addresses=_localized_from_json(row.addresses),
        service_areas=_localized_from_json(row.service_areas),
        parking_guidance=_localized_from_json(row.parking_guidance),
        payment_methods=tuple(row.payment_methods),
        warranty_policy=_localized_from_json(row.warranty_policy),
        appointment_policy=_localized_from_json(row.appointment_policy),
        version=row.version,
    )


def customer_to_row(entity: Customer) -> CustomerRow:
    phone = entity.phone
    return CustomerRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        display_name=entity.display_name,
        phone_raw=phone.raw if phone else None,
        phone_e164=phone.normalized_e164 if phone else None,
        phone_verified=phone.verified if phone else False,
        email=entity.email,
        locale=entity.locale.value,
        privacy_notice_version=entity.privacy_notice_version,
        privacy_accepted_at=entity.privacy_accepted_at,
        contact_consent_at=entity.contact_consent_at,
        status=entity.status.value,
    )


def customer_from_row(row: CustomerRow) -> Customer:
    phone = (
        PhoneNumber(row.phone_raw, row.phone_e164, row.phone_verified)
        if row.phone_raw is not None
        else None
    )
    return Customer(
        id=CustomerId(row.id),
        tenant_id=TenantId(row.tenant_id),
        locale=Locale(row.locale),
        display_name=row.display_name,
        phone=phone,
        email=row.email,
        privacy_notice_version=row.privacy_notice_version,
        privacy_accepted_at=row.privacy_accepted_at,
        contact_consent_at=row.contact_consent_at,
        status=CustomerStatus(row.status),
    )


def conversation_to_row(entity: Conversation) -> ConversationRow:
    return ConversationRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        customer_id=entity.customer_id.value,
        status=entity.status.value,
        locale=entity.locale.value,
        active_workflow=entity.active_workflow,
        last_message_at=entity.last_message_at,
    )


def conversation_from_row(row: ConversationRow) -> Conversation:
    return Conversation(
        id=ConversationId(row.id),
        tenant_id=TenantId(row.tenant_id),
        customer_id=CustomerId(row.customer_id),
        locale=Locale(row.locale),
        status=ConversationStatus(row.status),
        active_workflow=row.active_workflow,
        last_message_at=row.last_message_at,
    )


def category_to_row(entity: ServiceCategory) -> ServiceCategoryRow:
    return ServiceCategoryRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        names={key.value: value for key, value in entity.names.items()},
        sort_order=entity.sort_order,
        active=entity.active,
    )


def category_from_row(row: ServiceCategoryRow) -> ServiceCategory:
    return ServiceCategory(
        id=CategoryId(row.id),
        tenant_id=TenantId(row.tenant_id),
        names={Locale(key): value for key, value in row.names.items()},
        sort_order=row.sort_order,
        active=row.active,
    )


def service_to_row(entity: Service) -> ServiceRow:
    represented_money = entity.price.minimum or entity.price.maximum
    return ServiceRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        category_id=entity.category_id.value,
        code=entity.code,
        names={key.value: value for key, value in entity.names.items()},
        descriptions={key.value: value for key, value in entity.descriptions.items()},
        duration_seconds=int(entity.duration.total_seconds()),
        buffer_seconds=int(entity.cleanup_buffer.total_seconds()),
        price_mode=entity.price.mode.value,
        price_min_minor=entity.price.minimum.amount_minor if entity.price.minimum else None,
        price_max_minor=entity.price.maximum.amount_minor if entity.price.maximum else None,
        currency=represented_money.currency if represented_money is not None else None,
        preparation_notes={key.value: value for key, value in entity.preparation_notes.items()},
        eligibility_notes={key.value: value for key, value in entity.eligibility_notes.items()},
        active=entity.active,
        bookable=entity.bookable,
        version=entity.version,
    )


def service_from_row(row: ServiceRow) -> Service:
    minimum = (
        Money(row.price_min_minor, row.currency)
        if row.price_min_minor is not None and row.currency
        else None
    )
    maximum = (
        Money(row.price_max_minor, row.currency)
        if row.price_max_minor is not None and row.currency
        else None
    )
    return Service(
        id=ServiceId(row.id),
        tenant_id=TenantId(row.tenant_id),
        category_id=CategoryId(row.category_id),
        code=row.code,
        names={Locale(key): value for key, value in row.names.items()},
        descriptions={Locale(key): value for key, value in row.descriptions.items()},
        duration=timedelta(seconds=row.duration_seconds),
        cleanup_buffer=timedelta(seconds=row.buffer_seconds),
        price=PricePresentation(PriceMode(row.price_mode), minimum, maximum),
        preparation_notes={Locale(key): value for key, value in row.preparation_notes.items()},
        eligibility_notes={Locale(key): value for key, value in row.eligibility_notes.items()},
        active=row.active,
        bookable=row.bookable,
        version=row.version,
    )


def schedule_to_rows(
    entity: BusinessSchedule,
) -> tuple[BusinessScheduleRow, list[ScheduleIntervalRow], list[ScheduleOverrideRow]]:
    from uuid import uuid4

    schedule = BusinessScheduleRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        name=entity.name,
        timezone=entity.timezone,
        active=entity.active,
    )
    intervals = [
        ScheduleIntervalRow(
            id=uuid4(),
            tenant_id=entity.tenant_id.value,
            schedule_id=entity.id.value,
            weekday=item.weekday,
            start_local=item.start_local,
            end_local=item.end_local,
            interval_type=item.interval_type.value,
        )
        for item in entity.intervals
    ]
    overrides = [
        ScheduleOverrideRow(
            id=uuid4(),
            tenant_id=entity.tenant_id.value,
            schedule_id=entity.id.value,
            starts_on=item.starts_on,
            ends_on=item.ends_on,
            closed=item.closed,
            intervals=[
                {
                    "weekday": interval.weekday,
                    "start": interval.start_local.isoformat(),
                    "end": interval.end_local.isoformat(),
                    "type": interval.interval_type.value,
                }
                for interval in item.intervals
            ],
            reason=item.reason,
        )
        for item in entity.overrides
    ]
    return schedule, intervals, overrides


def schedule_from_rows(
    row: BusinessScheduleRow,
    interval_rows: list[ScheduleIntervalRow],
    override_rows: list[ScheduleOverrideRow],
) -> BusinessSchedule:
    from datetime import time

    intervals = tuple(
        ScheduleInterval(
            item.weekday, item.start_local, item.end_local, IntervalType(item.interval_type)
        )
        for item in interval_rows
    )
    overrides = tuple(
        ScheduleOverride(
            item.starts_on,
            item.ends_on,
            item.closed,
            tuple(
                ScheduleInterval(
                    int(raw["weekday"]),
                    time.fromisoformat(str(raw["start"])),
                    time.fromisoformat(str(raw["end"])),
                    IntervalType(str(raw["type"])),
                )
                for raw in item.intervals
            ),
            item.reason,
        )
        for item in override_rows
    )
    return BusinessSchedule(
        ScheduleId(row.id),
        TenantId(row.tenant_id),
        row.name,
        row.timezone,
        intervals,
        overrides,
        row.active,
    )


def booking_to_row(entity: Booking) -> BookingRow:
    return BookingRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        customer_id=entity.customer_id.value,
        service_id=entity.service_id.value,
        start_at=entity.time_range.start,
        end_at=entity.time_range.end,
        status=entity.status.value,
        idempotency_scope=entity.idempotency_key.scope,
        idempotency_value=entity.idempotency_key.value,
        idempotency_expires_at=entity.idempotency_key.expires_at,
        service_snapshot=dict(entity.service_snapshot),
        customer_snapshot=dict(entity.customer_snapshot),
    )


def booking_from_row(row: BookingRow) -> Booking:
    return Booking(
        BookingId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id),
        ServiceId(row.service_id),
        TimeRange(row.start_at, row.end_at),
        IdempotencyKey(row.idempotency_scope, row.idempotency_value, row.idempotency_expires_at),
        row.service_snapshot,
        row.customer_snapshot,
        BookingStatus(row.status),
    )


def lead_to_row(entity: Lead) -> LeadRow:
    return LeadRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        customer_id=entity.customer_id.value,
        conversation_id=entity.conversation_id.value,
        schema_code=entity.schema_code,
        schema_version=entity.schema_version,
        source=entity.source,
        answers=entity.answers,
        status=entity.status.value,
        score=entity.score,
        priority=entity.priority.value if entity.priority else None,
        score_explanation=dict(entity.score_explanation) if entity.score_explanation else None,
        consent_at=entity.consent_at,
        qualification_snapshot=(
            dict(entity.qualification_snapshot) if entity.qualification_snapshot else None
        ),
        qualified_at=entity.qualified_at,
    )


def lead_from_row(row: LeadRow) -> Lead:
    return Lead(
        LeadId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id),
        ConversationId(row.conversation_id),
        row.schema_code,
        row.schema_version,
        row.source,
        row.answers,
        LeadStatus(row.status),
        row.score,
        LeadPriority(row.priority) if row.priority else None,
        row.score_explanation,
        row.consent_at,
        row.qualification_snapshot,
        row.qualified_at,
    )


def handoff_to_row(entity: HandoffCase) -> HandoffCaseRow:
    return HandoffCaseRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        conversation_id=entity.conversation_id.value,
        reason_code=entity.reason_code,
        priority=entity.priority.value,
        status=entity.status.value,
        assignee_id=entity.assignee_id,
        summary=entity.summary,
        response_due_at=entity.response_due_at,
    )


def handoff_from_row(row: HandoffCaseRow) -> HandoffCase:
    return HandoffCase(
        HandoffId(row.id),
        TenantId(row.tenant_id),
        ConversationId(row.conversation_id),
        row.reason_code,
        HandoffPriority(row.priority),
        row.summary,
        row.response_due_at,
        HandoffStatus(row.status),
        row.assignee_id,
    )


def knowledge_to_row(entity: KnowledgeDocument) -> KnowledgeDocumentRow:
    return KnowledgeDocumentRow(
        id=entity.id.value,
        tenant_id=entity.tenant_id.value,
        title=entity.title,
        locale=entity.locale.value,
        source_type=entity.source_type,
        checksum=entity.checksum,
        version=entity.version,
        status=entity.status.value,
        published_at=entity.published_at,
        metadata_json={},
    )


def knowledge_from_row(row: KnowledgeDocumentRow) -> KnowledgeDocument:
    return KnowledgeDocument(
        DocumentId(row.id),
        TenantId(row.tenant_id),
        row.title,
        Locale(row.locale),
        row.source_type,
        row.checksum,
        row.version,
        KnowledgeStatus(row.status),
        row.published_at,
    )
