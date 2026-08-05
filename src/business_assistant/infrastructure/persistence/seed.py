"""Idempotent, non-production seed for the fictional Northstar demo tenant."""

import asyncio
import os
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from business_assistant.application.knowledge import content_checksum
from business_assistant.application.leads import (
    FieldValidation,
    GradeBand,
    HandoffTrigger,
    MatchOperator,
    QualificationField,
    QualificationFieldType,
    QualificationSchema,
    ScoreRule,
    Sensitivity,
)
from business_assistant.domain.catalog import Service, ServiceCategory
from business_assistant.domain.scheduling import (
    BusinessSchedule,
    ScheduleInterval,
    ScheduleOverride,
)
from business_assistant.domain.shared import (
    CategoryId,
    Locale,
    Money,
    PriceMode,
    PricePresentation,
    QualificationSchemaId,
    ScheduleId,
    ServiceId,
    TenantId,
)
from business_assistant.domain.tenants import Tenant, TenantPublicProfile

from .qualification import schema_definition
from .sqlalchemy.engine import create_engine, create_session_factory
from .sqlalchemy.models import (
    BookingPolicyRow,
    KnowledgeChunkRow,
    KnowledgeDocumentRow,
    QualificationSchemaRow,
    ResourceRow,
    RetentionPolicyRow,
    ServiceResourceRow,
    TenantEntitlementRow,
    TenantMemberRow,
)
from .sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork

NORTHSTAR_TENANT_ID = TenantId(UUID("f73f5ad0-05c8-5bc6-a2c7-166b959fa73e"))
NORTHSTAR_CATEGORY_ID = CategoryId(UUID("43ec952c-c4f4-5387-9cb9-cbe42dd16ef5"))
NORTHSTAR_SCHEDULE_ID = ScheduleId(UUID("9419ac4d-a535-5f3b-99f0-f51f6a6e042a"))
NORTHSTAR_RESOURCE_IDS = (
    UUID("ad08e178-17a7-5512-8734-cb6aff4018d0"),
    UUID("d1e30ca4-b9ba-59ca-8ae4-1962c6dc6eee"),
)
NORTHSTAR_QUALIFICATION_SCHEMA_ID = QualificationSchemaId(
    UUID("2ab5519f-f966-5cd5-8338-9c1df89eeb1c")
)
NORTHSTAR_KNOWLEDGE_DOCUMENT_ID = UUID("de5a471b-985c-5884-91f4-2a91ea789b4f")
NORTHSTAR_KNOWLEDGE_CHUNK_ID = UUID("2242d718-3cf2-5ed5-8581-6dadf62955a7")
NORTHSTAR_OWNER_MEMBER_ID = UUID("06d54aa7-b1e2-5208-aa69-fc104231212e")
_NORTHSTAR_FAQ_TEXT = (
    "Question: Do you guarantee same-day repairs?\n"
    "Answer: No. Completion time depends on inspection findings and parts availability. "
    "The fictional workshop confirms timing after inspection."
)

_SERVICE_IDS = {
    "oil-change": ServiceId(UUID("ec416e09-15a1-54a4-9553-01d97b1b83e4")),
    "brake-inspection": ServiceId(UUID("056faeb8-a8aa-52f8-8071-1fa2fd8aa60c")),
    "engine-diagnostics": ServiceId(UUID("b2bdbfa5-57ab-5957-8e31-d3f0828a4f76")),
    "tire-service": ServiceId(UUID("4f08309c-fe77-5d89-ab05-fce2d454f3cd")),
    "battery-replacement": ServiceId(UUID("1030e2e0-6350-5201-a51f-a77c83d406d7")),
    "suspension-inspection": ServiceId(UUID("fc6cabdb-f03a-512b-b218-3ed555c9174e")),
}


def _service(
    code: str,
    english_name: str,
    duration_minutes: int,
    price_mode: PriceMode,
    starting_price_minor: int | None,
) -> Service:
    price = PricePresentation(
        price_mode,
        Money(starting_price_minor, "RUB") if starting_price_minor is not None else None,
    )
    return Service(
        id=_SERVICE_IDS[code],
        tenant_id=NORTHSTAR_TENANT_ID,
        category_id=NORTHSTAR_CATEGORY_ID,
        code=code,
        names={Locale.EN: english_name},
        descriptions={
            Locale.EN: f"{english_name} appointment at the fictional Northstar workshop."
        },
        duration=timedelta(minutes=duration_minutes),
        cleanup_buffer=timedelta(minutes=10),
        price=price,
        preparation_notes={
            Locale.EN: "Bring the vehicle registration and describe observed symptoms."
        },
    )


def northstar_services() -> tuple[Service, ...]:
    # Demo-only durations/prices are synthetic defaults, not real offers or universal policy.
    return (
        _service("oil-change", "Oil change", 45, PriceMode.EXACT, 450_000),
        _service(
            "brake-inspection",
            "Brake inspection",
            60,
            PriceMode.STARTING_FROM,
            300_000,
        ),
        _service(
            "engine-diagnostics",
            "Engine diagnostics",
            90,
            PriceMode.STARTING_FROM,
            500_000,
        ),
        _service("tire-service", "Tire service", 60, PriceMode.EXACT, 400_000),
        _service(
            "battery-replacement",
            "Battery replacement",
            45,
            PriceMode.QUOTE_REQUIRED,
            None,
        ),
        _service(
            "suspension-inspection",
            "Suspension inspection",
            60,
            PriceMode.STARTING_FROM,
            350_000,
        ),
    )


def northstar_qualification_schema() -> QualificationSchema:
    safety_triggers = tuple(
        HandoffTrigger(
            f"issue-{phrase.replace(' ', '-')}",
            MatchOperator.CONTAINS,
            phrase,
            phrase.replace(" ", "_"),
            "urgent",
        )
        for phrase in ("accident", "fire", "fuel leak")
    )
    return QualificationSchema(
        NORTHSTAR_QUALIFICATION_SCHEMA_ID,
        NORTHSTAR_TENANT_ID,
        "service_request",
        1,
        "Vehicle service request",
        "northstar-demo-v1",
        "Store these details to prepare and respond to this fictional service request.",
        (
            QualificationField(
                "vehicle",
                "Vehicle",
                "What is the vehicle make, model, and year?",
                QualificationFieldType.SHORT_TEXT,
                FieldValidation(min_length=3, max_length=100),
                True,
                0,
                Sensitivity.PERSONAL,
            ),
            QualificationField(
                "issue",
                "Observed issue",
                "Briefly describe what you observed. Do not rely on this demo for a diagnosis.",
                QualificationFieldType.LONG_TEXT,
                FieldValidation(min_length=5, max_length=500),
                True,
                1,
                Sensitivity.PERSONAL,
                handoff_triggers=safety_triggers,
            ),
            QualificationField(
                "drivable",
                "Vehicle drivable",
                "Is the vehicle currently safe to move? Answer yes or no. If unsure, answer no.",
                QualificationFieldType.BOOLEAN,
                FieldValidation(),
                True,
                2,
                Sensitivity.SENSITIVE,
                score_rules=(ScoreRule("not-drivable-score", MatchOperator.EQUALS, False, 40),),
                handoff_triggers=(
                    HandoffTrigger(
                        "not-drivable",
                        MatchOperator.EQUALS,
                        False,
                        "unsafe_vehicle",
                        "urgent",
                    ),
                ),
            ),
            QualificationField(
                "urgency",
                "Requested timing",
                "Choose a timing: Routine, Soon, or Urgent.",
                QualificationFieldType.SINGLE_CHOICE,
                FieldValidation(options=("Routine", "Soon", "Urgent")),
                True,
                3,
                Sensitivity.PUBLIC,
                score_rules=(
                    ScoreRule("timing-routine", MatchOperator.EQUALS, "Routine", 10),
                    ScoreRule("timing-soon", MatchOperator.EQUALS, "Soon", 30),
                    ScoreRule("timing-urgent", MatchOperator.EQUALS, "Urgent", 60),
                ),
            ),
            QualificationField(
                "contact_phone",
                "Contact phone",
                "Enter a phone number the fictional workshop may use for this request.",
                QualificationFieldType.PHONE,
                FieldValidation(),
                True,
                4,
                Sensitivity.SENSITIVE,
            ),
        ),
        (GradeBand(0, "C"), GradeBand(30, "B"), GradeBand(60, "A")),
        timedelta(hours=24),
        120,
        True,
        True,
    )


async def seed_northstar(database_url: str, app_env: str) -> None:
    if app_env not in {"local", "development", "test"}:
        raise RuntimeError("Northstar demo seed is disabled outside local/development/test")
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    try:
        async with SQLAlchemyUnitOfWork(factory) as uow:
            await uow.tenants.upsert(
                NORTHSTAR_TENANT_ID,
                Tenant(
                    NORTHSTAR_TENANT_ID,
                    "northstar-auto-care",
                    "Northstar Auto Care (fictional demo)",
                    "Europe/Moscow",
                    Locale.EN,
                    frozenset({Locale.EN}),
                ),
            )
            await uow.categories.upsert(
                NORTHSTAR_TENANT_ID,
                ServiceCategory(
                    NORTHSTAR_CATEGORY_ID,
                    NORTHSTAR_TENANT_ID,
                    {Locale.EN: "Auto care"},
                ),
            )
            intervals = (
                *(ScheduleInterval(day, time(8), time(12)) for day in range(5)),
                *(ScheduleInterval(day, time(13), time(18)) for day in range(5)),
                ScheduleInterval(5, time(9), time(15)),
            )
            overrides = (
                ScheduleOverride(date(2027, 1, 1), date(2027, 1, 1), True, reason="Demo holiday"),
                ScheduleOverride(
                    date(2027, 1, 3),
                    date(2027, 1, 3),
                    False,
                    (ScheduleInterval(6, time(10), time(14)),),
                    "Demo special opening",
                ),
            )
            await uow.schedules.replace(
                NORTHSTAR_TENANT_ID,
                BusinessSchedule(
                    NORTHSTAR_SCHEDULE_ID,
                    NORTHSTAR_TENANT_ID,
                    "Workshop hours",
                    "Europe/Moscow",
                    intervals,
                    overrides,
                ),
            )
            await uow.public_profiles.upsert(
                NORTHSTAR_TENANT_ID,
                TenantPublicProfile(
                    tenant_id=NORTHSTAR_TENANT_ID,
                    schedule_id=NORTHSTAR_SCHEDULE_ID,
                    descriptions={
                        Locale.EN: "Fictional auto-care workshop for the portfolio demonstration."
                    },
                    public_phone="+1 555 010 0200",
                    public_email="hello@northstar.example",
                    website_url="https://northstar.example",
                    addresses={Locale.EN: "18 Harbor Road"},
                    parking_guidance={
                        Locale.EN: "Customer parking is beside the workshop entrance."
                    },
                    payment_methods=("cash", "card"),
                    warranty_policy={
                        Locale.EN: "Warranty terms depend on the approved service and parts."
                    },
                    appointment_policy={Locale.EN: "Appointments require workshop confirmation."},
                ),
            )
            for service in northstar_services():
                await uow.services.upsert(NORTHSTAR_TENANT_ID, service)
            await uow.commit()
        async with factory() as session, session.begin():
            await session.execute(
                insert(TenantMemberRow)
                .values(
                    id=NORTHSTAR_OWNER_MEMBER_ID,
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    subject="northstar-demo-owner",
                    role="owner",
                    active=True,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "subject"])
            )
            for capability in (
                "telegram",
                "booking",
                "qualification",
                "ai_routing",
                "knowledge_answers",
                "background_notifications",
            ):
                await session.execute(
                    insert(TenantEntitlementRow)
                    .values(
                        tenant_id=NORTHSTAR_TENANT_ID.value,
                        capability=capability,
                        enabled=True,
                        version=1,
                    )
                    .on_conflict_do_nothing(index_elements=["tenant_id", "capability"])
                )
            await session.execute(
                insert(RetentionPolicyRow)
                .values(
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    version=1,
                    operational_metadata_days=30,
                    message_content_days=90,
                    customer_contact_days=365,
                    workflow_records_days=730,
                    knowledge_archive_days=365,
                    ai_telemetry_days=90,
                    automatic_execution_enabled=False,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id"])
            )
            qualification = northstar_qualification_schema()
            await session.execute(
                insert(QualificationSchemaRow)
                .values(
                    id=qualification.id.value,
                    tenant_id=qualification.tenant_id.value,
                    code=qualification.code,
                    version=qualification.version,
                    title=qualification.title,
                    consent_version=qualification.consent_version,
                    consent_purpose=qualification.consent_purpose,
                    definition=schema_definition(qualification),
                    grade_bands=[
                        {"minimum_score": band.minimum_score, "grade": band.grade}
                        for band in qualification.grade_bands
                    ],
                    session_ttl_minutes=int(qualification.session_ttl.total_seconds() // 60),
                    handoff_response_minutes=qualification.handoff_response_minutes,
                    published=qualification.published,
                    active=qualification.active,
                    config_version=1,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "title": qualification.title,
                        "consent_version": qualification.consent_version,
                        "consent_purpose": qualification.consent_purpose,
                        "definition": schema_definition(qualification),
                        "grade_bands": [
                            {"minimum_score": band.minimum_score, "grade": band.grade}
                            for band in qualification.grade_bands
                        ],
                        "session_ttl_minutes": int(qualification.session_ttl.total_seconds() // 60),
                        "handoff_response_minutes": qualification.handoff_response_minutes,
                        "published": True,
                        "active": True,
                    },
                )
            )
            await session.execute(
                insert(BookingPolicyRow)
                .values(
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    slot_interval_minutes=30,
                    booking_horizon_days=30,
                    minimum_notice_minutes=120,
                    hold_duration_minutes=5,
                    draft_expiry_minutes=30,
                    change_cutoff_minutes=1440,
                    customer_name_max_length=100,
                    customer_phone_max_length=32,
                    customer_note_max_length=500,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id"],
                    set_={
                        "slot_interval_minutes": 30,
                        "booking_horizon_days": 30,
                        "minimum_notice_minutes": 120,
                        "hold_duration_minutes": 5,
                        "draft_expiry_minutes": 30,
                        "change_cutoff_minutes": 1440,
                        "customer_name_max_length": 100,
                        "customer_phone_max_length": 32,
                        "customer_note_max_length": 500,
                    },
                )
            )
            knowledge_checksum = content_checksum(_NORTHSTAR_FAQ_TEXT)
            await session.execute(
                insert(KnowledgeDocumentRow)
                .values(
                    id=NORTHSTAR_KNOWLEDGE_DOCUMENT_ID,
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    title="Same-day repair FAQ",
                    locale="en",
                    source_type="faq",
                    checksum=knowledge_checksum,
                    source_text=_NORTHSTAR_FAQ_TEXT,
                    version=1,
                    status="ready",
                    published_at=datetime(2026, 8, 4, tzinfo=UTC),
                    metadata_json={"fictional_demo": True},
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "title": "Same-day repair FAQ",
                        "source_text": _NORTHSTAR_FAQ_TEXT,
                        "checksum": knowledge_checksum,
                        "status": "ready",
                        "published_at": datetime(2026, 8, 4, tzinfo=UTC),
                    },
                )
            )
            await session.execute(
                insert(KnowledgeChunkRow)
                .values(
                    id=NORTHSTAR_KNOWLEDGE_CHUNK_ID,
                    tenant_id=NORTHSTAR_TENANT_ID.value,
                    document_id=NORTHSTAR_KNOWLEDGE_DOCUMENT_ID,
                    document_version=1,
                    ordinal=0,
                    chunk_text=_NORTHSTAR_FAQ_TEXT,
                    token_count=len(_NORTHSTAR_FAQ_TEXT.split()),
                    embedding=None,
                    embedding_model=None,
                    embedding_dimensions=None,
                    instruction_risk=False,
                    metadata_json={"section": "FAQ", "priority": 50},
                    checksum=knowledge_checksum,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "chunk_text": _NORTHSTAR_FAQ_TEXT,
                        "token_count": len(_NORTHSTAR_FAQ_TEXT.split()),
                        "instruction_risk": False,
                        "metadata": {"section": "FAQ", "priority": 50},
                        "checksum": knowledge_checksum,
                    },
                )
            )
            for resource_id in NORTHSTAR_RESOURCE_IDS:
                await session.execute(
                    insert(ResourceRow)
                    .values(
                        id=resource_id,
                        tenant_id=NORTHSTAR_TENANT_ID.value,
                        schedule_id=NORTHSTAR_SCHEDULE_ID.value,
                        resource_type="service_bay",
                        capacity=1,
                        active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "schedule_id": NORTHSTAR_SCHEDULE_ID.value,
                            "resource_type": "service_bay",
                            "capacity": 1,
                            "active": True,
                        },
                    )
                )
            for service_id in _SERVICE_IDS.values():
                for resource_id in NORTHSTAR_RESOURCE_IDS:
                    assignment_id = UUID(
                        bytes=bytes(
                            a ^ b
                            for a, b in zip(service_id.value.bytes, resource_id.bytes, strict=True)
                        )
                    )
                    await session.execute(
                        insert(ServiceResourceRow)
                        .values(
                            id=assignment_id,
                            tenant_id=NORTHSTAR_TENANT_ID.value,
                            service_id=service_id.value,
                            resource_id=resource_id,
                            required_capacity=1,
                            active=True,
                        )
                        .on_conflict_do_update(
                            constraint="uq_service_resources_tenant_id_service_id_resource_id",
                            set_={"required_capacity": 1, "active": True},
                        )
                    )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    asyncio.run(seed_northstar(database_url, os.environ.get("APP_ENV", "")))


if __name__ == "__main__":
    main()
