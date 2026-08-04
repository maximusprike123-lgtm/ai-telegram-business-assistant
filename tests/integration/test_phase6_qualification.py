from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.helpers_phase3 import api_services, phase3_fixture

from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import AuthorizationError
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.handoffs import HandoffApplication
from business_assistant.application.leads import (
    QualificationAdministration,
    QualificationApplication,
)
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import QualificationSchemaId, QualificationSessionId
from business_assistant.infrastructure.persistence import (
    SQLAlchemyHandoffStore,
    SQLAlchemyQualificationStore,
    SQLAlchemyTelegramIdentityStore,
)
from business_assistant.infrastructure.persistence.seed import (
    NORTHSTAR_TENANT_ID,
    seed_northstar,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    AuditEventRow,
    ConversationRow,
    HandoffCaseRow,
    LeadRow,
    OutboxEventRow,
    QualificationConsentRow,
    QualificationSchemaRow,
    QualificationSessionRow,
    QualificationSessionUpdateRow,
)
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)
from business_assistant.presentation.http import create_phase3_app
from business_assistant.presentation.telegram import TelegramRenderer
from business_assistant.presentation.telegram.navigation import (
    TelegramNavigation,
    TelegramNavigationServices,
)

pytestmark = pytest.mark.postgresql
NOW = datetime(2026, 8, 3, 7, tzinfo=UTC)


@dataclass(frozen=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


async def identity(factory: async_sessionmaker[AsyncSession], external_id: int):
    return await SQLAlchemyTelegramIdentityStore(factory).resolve(
        NORTHSTAR_TENANT_ID,
        external_user_id=str(external_id),
        external_chat_id=str(external_id),
        requested_locale="en",
        now=NOW,
    )


@pytest.mark.asyncio
async def test_seeded_qualification_resumes_corrects_edits_scores_and_escalates_atomically(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 6001)
    store = SQLAlchemyQualificationStore(factory)
    app = QualificationApplication(store, FixedClock(), schema_code="service_request")

    session, initial_schema = await app.start(owner)
    assert session.status.value == "awaiting_consent"
    resumed, _ = await app.start(owner)
    assert resumed.id == session.id
    next_schema = await store.add_schema(
        replace(
            initial_schema,
            id=QualificationSchemaId.new(),
            version=2,
            consent_version="northstar-demo-v2",
            published=False,
        )
    )
    await store.publish_schema(owner.tenant_id, next_schema.id)
    active = await app.active(owner)
    assert active is not None and active[1].version == 1
    session, first = await app.consent(owner, session.id, True, "callback:consent")
    assert first is not None and first.key == "vehicle"

    with pytest.raises(ValueError, match="at least 3"):
        await app.answer(owner, "x", "message:invalid")

    answers = (
        ("2019 Northstar Demo", "message:1"),
        ("A fuel leak is visible", "message:2"),
        ("no", "message:3"),
        ("Urgent", "message:4"),
        ("+1 555 010 0199", "message:5"),
    )
    for value, key in answers:
        session, _ = await app.answer(owner, value, key)
    assert session.status.value == "reviewing"

    edited = await app.edit(owner, session.id, "vehicle")
    assert edited.key == "vehicle"
    session, next_field = await app.answer(owner, "2020 Northstar Demo", "message:edit")
    assert next_field is None and session.status.value == "reviewing"
    completed = await app.submit(owner, session.id, "callback:submit")
    assert completed.status.value == "completed"
    assert completed.lead_id is not None

    async with factory() as sql:
        lead = await sql.scalar(select(LeadRow))
        handoff = await sql.scalar(select(HandoffCaseRow))
        conversation = await sql.get(ConversationRow, owner.conversation_id.value)
        event_types = set((await sql.scalars(select(OutboxEventRow.event_type))).all())
        update_count = await sql.scalar(
            select(func.count()).select_from(QualificationSessionUpdateRow)
        )
    assert lead is not None
    assert lead.score == 100 and lead.score_explanation["grade"] == "A"
    assert lead.qualification_snapshot["schema_version"] == 1
    assert lead.qualified_at == NOW
    assert handoff is not None and handoff.reason_code == "unsafe_vehicle"
    assert handoff.priority == "urgent"
    assert handoff.context["matched_rules"] == ["issue-fuel-leak", "not-drivable"]
    assert conversation is not None and conversation.status == "handoff_queued"
    assert event_types == {"lead.qualified", "handoff.queued"}
    assert update_count == 8


@pytest.mark.asyncio
async def test_consent_decline_is_persisted_and_terminates_without_lead(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 6002)
    store = SQLAlchemyQualificationStore(factory)
    app = QualificationApplication(store, FixedClock(), schema_code="service_request")
    started, _ = await app.start(owner)
    declined, field = await app.consent(owner, started.id, False, "callback:decline")
    assert declined.status.value == "declined" and field is None
    assert await app.active(owner) is None
    async with factory() as sql:
        consent = await sql.scalar(select(QualificationConsentRow))
        lead_count = await sql.scalar(select(func.count()).select_from(LeadRow))
        conversation = await sql.get(ConversationRow, owner.conversation_id.value)
    assert consent is not None
    assert (consent.decision, consent.consent_version) == ("declined", "northstar-demo-v1")
    assert "fictional service request" in consent.purpose
    assert lead_count == 0
    assert conversation is not None and conversation.active_workflow is None

    cancelled, _ = await app.start(owner)
    assert await app.cancel(owner) is True
    expired, _ = await app.start(owner)
    assert expired.id != cancelled.id
    assert await store.active_session(owner, now=NOW + timedelta(days=2)) is None
    async with factory() as sql:
        statuses = list((await sql.scalars(select(QualificationSessionRow.status))).all())
    assert sorted(statuses) == ["cancelled", "declined", "expired"]


@pytest.mark.asyncio
async def test_session_update_and_handoff_creation_are_idempotent_and_tenant_scoped(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 6003)
    qualification = SQLAlchemyQualificationStore(factory)
    schema = await qualification.published_schema(owner.tenant_id, "service_request")
    assert schema is not None
    session = await qualification.start(owner, schema, now=NOW)
    await qualification.decide_consent(
        owner, session.id, schema_decision(), now=NOW, update_key="duplicate-consent"
    )
    repeated = await qualification.decide_consent(
        owner, session.id, schema_decision(), now=NOW, update_key="duplicate-consent"
    )
    assert repeated.status.value == "in_progress"

    handoffs = HandoffApplication(SQLAlchemyHandoffStore(factory), FixedClock())
    first = await handoffs.request(
        owner,
        reason_code="explicit_manager_request",
        priority="normal",
        summary="Customer requested a person.",
        idempotency_key="telegram-human:6003",
    )
    repeated_handoff = await handoffs.request(
        owner,
        reason_code="explicit_manager_request",
        priority="normal",
        summary="Customer requested a person.",
        idempotency_key="telegram-human:6003",
    )
    assert repeated_handoff.id == first.id

    viewer = Principal("viewer", owner.tenant_id, Role.VIEWER)
    with pytest.raises(AuthorizationError):
        await handoffs.transition(viewer, first.id, "claim")
    agent = Principal("staff-1", owner.tenant_id, Role.AGENT)
    assert (await handoffs.transition(agent, first.id, "claim")).status == "claimed"
    assert (await handoffs.transition(agent, first.id, "resolve")).status == "resolved"
    assert (await handoffs.transition(agent, first.id, "reopen")).status == "reopened"
    assert (await handoffs.transition(agent, first.id, "claim")).status == "claimed"
    assert (await handoffs.transition(agent, first.id, "resolve")).status == "resolved"
    assert (await handoffs.transition(agent, first.id, "return_to_bot")).status == "resolved"
    async with factory() as sql:
        count = await sql.scalar(select(func.count()).select_from(HandoffCaseRow))
        audits = await sql.scalar(select(func.count()).select_from(AuditEventRow))
        conversation = await sql.get(ConversationRow, owner.conversation_id.value)
        schemas = await sql.scalar(select(func.count()).select_from(QualificationSchemaRow))
        sessions = await sql.scalar(select(func.count()).select_from(QualificationSessionRow))
    assert count == 1 and audits == 6
    assert conversation is not None and conversation.status == "active_bot"
    assert schemas == sessions == 1


def schema_decision():
    from business_assistant.application.leads import ConsentDecision

    return ConsentDecision.ACCEPTED


@pytest.mark.asyncio
async def test_phase6_internal_api_documents_schema_and_authorized_handoff_operations(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 6004)
    qualification_store = SQLAlchemyQualificationStore(factory)
    handoff_app = HandoffApplication(SQLAlchemyHandoffStore(factory), FixedClock())
    handoff = await handoff_app.request(
        owner,
        reason_code="explicit_manager_request",
        priority="normal",
        summary="Customer requested a person.",
        idempotency_key="api-handoff",
    )
    uow, _, clock, key = phase3_fixture()
    manager = Principal("manager-1", NORTHSTAR_TENANT_ID, Role.MANAGER)
    services = replace(
        api_services(uow, manager, clock, key),
        qualification_admin=QualificationAdministration(qualification_store),
        handoffs=handoff_app,
    )
    app = create_phase3_app(services)
    headers = {"X-Internal-API-Key": key}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        schemas = await client.get("/api/v1/qualification-schemas", headers=headers)
        assert schemas.status_code == 200
        assert schemas.json()[0]["code"] == "service_request"
        created = await client.post(
            "/api/v1/qualification-schemas",
            headers=headers,
            json={
                "code": "fleet_request",
                "version": 1,
                "title": "Fleet request",
                "consent_version": "demo-v1",
                "consent_purpose": "Prepare a fictional fleet request.",
                "fields": [
                    {
                        "key": "fleet_size",
                        "label": "Fleet size",
                        "prompt": "How many vehicles are in the fleet?",
                        "field_type": "integer",
                        "validation": {"minimum": 1, "maximum": 1000},
                        "required": True,
                        "order": 0,
                        "sensitivity": "personal",
                    }
                ],
                "grade_bands": [{"minimum_score": 0, "grade": "C"}],
                "session_ttl_minutes": 60,
                "handoff_response_minutes": 120,
                "active": True,
            },
        )
        assert created.status_code == 201 and created.json()["published"] is False
        schema_id = created.json()["id"]
        published = await client.post(
            f"/api/v1/qualification-schemas/{schema_id}/publish", headers=headers
        )
        assert published.status_code == 200 and published.json()["published"] is True
        open_cases = await client.get("/api/v1/handoffs", headers=headers)
        assert open_cases.status_code == 200 and open_cases.json()[0]["id"] == str(handoff.id)
        claimed = await client.post(
            f"/api/v1/handoffs/{handoff.id}/actions",
            headers=headers,
            json={"action": "claim"},
        )
        assert claimed.status_code == 200 and claimed.json()["status"] == "claimed"
        openapi = (await client.get("/openapi.json")).json()
        assert "/api/v1/qualification-schemas" in openapi["paths"]
        assert "/api/v1/handoffs/{handoff_id}/actions" in openapi["paths"]

    viewer = Principal("viewer-1", NORTHSTAR_TENANT_ID, Role.VIEWER)
    viewer_app = create_phase3_app(
        replace(
            api_services(uow, viewer, clock, key),
            qualification_admin=QualificationAdministration(qualification_store),
            handoffs=handoff_app,
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=viewer_app), base_url="http://test"
    ) as client:
        denied = await client.post(
            f"/api/v1/qualification-schemas/{schema_id}/publish",
            headers=headers,
        )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_telegram_qualification_review_edit_submit_and_handoff_pause_are_persisted(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = database
    await seed_northstar(postgresql_url, "test")
    owner = await identity(factory, 6005)
    clock = FixedClock()
    renderer = TelegramRenderer()

    def uow_factory() -> Phase3UnitOfWork:
        return cast(Phase3UnitOfWork, SQLAlchemyUnitOfWork(factory))

    typed_factory: Phase3UnitOfWorkFactory = uow_factory
    qualification = QualificationApplication(
        SQLAlchemyQualificationStore(factory), clock, schema_code="service_request"
    )
    handoffs = HandoffApplication(SQLAlchemyHandoffStore(factory), clock)
    navigation = TelegramNavigation(
        TelegramNavigationServices(
            GetTenantPublicProfile(typed_factory, clock),
            ListServiceCategories(typed_factory),
            ListServices(typed_factory),
            GetService(typed_factory),
            GetBusinessHours(typed_factory),
            GetBusinessStatus(typed_factory, clock),
            GetNextOpening(typed_factory, clock),
            renderer,
            qualifications=qualification,
            handoffs=handoffs,
        )
    )
    consent = await navigation.start_qualification(owner)
    assert "Consent version" in consent.text
    session_value = consent.button_rows[0][0].entity_id
    assert session_value is not None
    session_id = QualificationSessionId.parse(session_value)
    question = await navigation.qualification_consent(
        owner,
        session_id,
        accepted=True,
        update_key="telegram:consent",
    )
    assert "make, model, and year" in question.text
    page = None
    for index, value in enumerate(
        (
            "2021 Northstar Demo",
            "Routine maintenance request",
            "yes",
            "Routine",
            "+1 555 010 0155",
        )
    ):
        page = await navigation.qualification_text(owner, value, f"telegram:message:{index}")
    assert page is not None and "Review your service request" in page.text
    assert "ending 0155" in page.text and "+1 555" not in page.text
    edit = next(
        button for row in page.button_rows for button in row if button.label == "Edit Vehicle"
    )
    assert edit.entity_id is not None and edit.page is not None
    await navigation.edit_qualification(
        owner, QualificationSessionId.parse(edit.entity_id), edit.page
    )
    review = await navigation.qualification_text(owner, "2022 Northstar Demo", "telegram:edit")
    assert review is not None and "2022 Northstar Demo" in review.text
    submitted = await navigation.submit_qualification(owner, session_id, "telegram:submit")
    assert "Service request submitted" in submitted.text
    async with factory() as sql:
        original_lead = await sql.scalar(select(LeadRow))
    assert original_lead is not None

    second_consent = await navigation.start_qualification(owner)
    second_value = second_consent.button_rows[0][0].entity_id
    assert second_value is not None
    second_id = QualificationSessionId.parse(second_value)
    await navigation.qualification_consent(
        owner, second_id, accepted=True, update_key="telegram:consent:second"
    )
    for index, value in enumerate(
        (
            "2023 Northstar Demo",
            "Updated maintenance request",
            "yes",
            "Soon",
            "+1 555 010 0155",
        )
    ):
        await navigation.qualification_text(owner, value, f"telegram:second:{index}")
    await navigation.submit_qualification(owner, second_id, "telegram:submit:second")
    async with factory() as sql:
        updated_leads = list((await sql.scalars(select(LeadRow))).all())
    assert len(updated_leads) == 1
    assert updated_leads[0].id == original_lead.id
    assert updated_leads[0].answers["vehicle"] == "2023 Northstar Demo"

    handed_off = await navigation.human_help(owner, update_key="telegram:human")
    assert "Human help" in handed_off.text and "Bot replies are paused" in handed_off.text
    assert await navigation.paused(owner) is not None
