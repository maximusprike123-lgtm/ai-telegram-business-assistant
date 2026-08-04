"""PostgreSQL transactions for Phase 6 qualification and human handoff."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.handoffs import HandoffView
from business_assistant.application.leads import (
    Answer,
    ConsentDecision,
    FieldValidation,
    GradeBand,
    HandoffTrigger,
    MatchOperator,
    QualificationField,
    QualificationFieldType,
    QualificationSchema,
    QualificationSession,
    QualificationSessionStatus,
    ScoreResult,
    ScoreRule,
    Sensitivity,
    TriggerResult,
    next_missing_field,
)
from business_assistant.application.scheduling.engine import business_due_at
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.handoffs import (
    HandoffStatus,
)
from business_assistant.domain.leads import Lead
from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import (
    ConversationId,
    CustomerId,
    HandoffId,
    LeadId,
    QualificationSchemaId,
    QualificationSessionId,
    TenantId,
)

from .sqlalchemy.mappers import (
    handoff_from_row,
    handoff_to_row,
    lead_from_row,
    lead_to_row,
    schedule_from_rows,
)
from .sqlalchemy.models import (
    AuditEventRow,
    BusinessScheduleRow,
    ConversationRow,
    HandoffCaseRow,
    LeadRow,
    OutboxEventRow,
    QualificationConsentRow,
    QualificationSchemaRow,
    QualificationSessionRow,
    QualificationSessionUpdateRow,
    ScheduleIntervalRow,
    ScheduleOverrideRow,
    TenantPublicProfileRow,
)


def _validation(value: dict[str, Any]) -> FieldValidation:
    return FieldValidation(
        value.get("min_length"),
        value.get("max_length"),
        Decimal(value["minimum"]) if value.get("minimum") is not None else None,
        Decimal(value["maximum"]) if value.get("maximum") is not None else None,
        tuple(value.get("options", ())),
        value.get("pattern"),
    )


def _rule_expected(value: object, field_type: QualificationFieldType) -> str | int | Decimal | bool:
    if field_type is QualificationFieldType.DECIMAL:
        return Decimal(str(value))
    if field_type is QualificationFieldType.INTEGER:
        return int(str(value))
    if field_type is QualificationFieldType.BOOLEAN:
        return bool(value)
    return str(value)


def _schema(row: QualificationSchemaRow) -> QualificationSchema:
    fields = []
    for item in row.definition:
        field_type = QualificationFieldType(item["field_type"])
        fields.append(
            QualificationField(
                item["key"],
                item["label"],
                item["prompt"],
                field_type,
                _validation(item["validation"]),
                item["required"],
                item["order"],
                Sensitivity(item["sensitivity"]),
                tuple(
                    ScoreRule(
                        rule["code"],
                        MatchOperator(rule["operator"]),
                        _rule_expected(rule["expected"], field_type),
                        rule["points"],
                    )
                    for rule in item.get("score_rules", ())
                ),
                tuple(
                    HandoffTrigger(
                        rule["code"],
                        MatchOperator(rule["operator"]),
                        _rule_expected(rule["expected"], field_type),
                        rule["reason_code"],
                        rule["priority"],
                    )
                    for rule in item.get("handoff_triggers", ())
                ),
            )
        )
    return QualificationSchema(
        QualificationSchemaId(row.id),
        TenantId(row.tenant_id),
        row.code,
        row.version,
        row.title,
        row.consent_version,
        row.consent_purpose,
        tuple(fields),
        tuple(GradeBand(item["minimum_score"], item["grade"]) for item in row.grade_bands),
        timedelta(minutes=row.session_ttl_minutes),
        row.handoff_response_minutes,
        row.published,
        row.active,
    )


def schema_definition(schema: QualificationSchema) -> list[dict[str, Any]]:
    return [
        {
            "key": field.key,
            "label": field.label,
            "prompt": field.prompt,
            "field_type": field.field_type.value,
            "validation": {
                "min_length": field.validation.min_length,
                "max_length": field.validation.max_length,
                "minimum": str(field.validation.minimum)
                if field.validation.minimum is not None
                else None,
                "maximum": str(field.validation.maximum)
                if field.validation.maximum is not None
                else None,
                "options": list(field.validation.options),
                "pattern": field.validation.pattern,
            },
            "required": field.required,
            "order": field.order,
            "sensitivity": field.sensitivity.value,
            "score_rules": [
                {
                    "code": rule.code,
                    "operator": rule.operator.value,
                    "expected": str(rule.expected)
                    if isinstance(rule.expected, Decimal)
                    else rule.expected,
                    "points": rule.points,
                }
                for rule in field.score_rules
            ],
            "handoff_triggers": [
                {
                    "code": rule.code,
                    "operator": rule.operator.value,
                    "expected": str(rule.expected)
                    if isinstance(rule.expected, Decimal)
                    else rule.expected,
                    "reason_code": rule.reason_code,
                    "priority": rule.priority,
                }
                for rule in field.handoff_triggers
            ],
        }
        for field in schema.fields
    ]


def _stored_answer(value: Answer) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return value


def _answer(value: Any, kind: QualificationFieldType) -> Answer:
    if kind is QualificationFieldType.DECIMAL:
        return Decimal(str(value))
    if kind is QualificationFieldType.DATE:
        return date.fromisoformat(str(value))
    if kind is QualificationFieldType.MULTI_CHOICE:
        return tuple(str(item) for item in value)
    if kind is QualificationFieldType.INTEGER:
        return int(value)
    if kind is QualificationFieldType.BOOLEAN:
        return bool(value)
    return str(value)


def _session(row: QualificationSessionRow, schema: QualificationSchema) -> QualificationSession:
    field_types = {item.key: item.field_type for item in schema.fields}
    answers = {
        key: _answer(value, field_types[key])
        for key, value in row.answers.items()
        if key in field_types
    }
    return QualificationSession(
        QualificationSessionId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id),
        ConversationId(row.conversation_id),
        QualificationSchemaId(row.schema_id),
        row.schema_code,
        row.schema_version,
        QualificationSessionStatus(row.status),
        answers,
        row.current_field_key,
        row.expires_at,
        ConsentDecision(row.consent_decision) if row.consent_decision else None,
        row.consent_at,
        LeadId(row.lead_id) if row.lead_id else None,
    )


def _handoff_view(row: HandoffCaseRow) -> HandoffView:
    return HandoffView(
        HandoffId(row.id),
        TenantId(row.tenant_id),
        CustomerId(row.customer_id) if row.customer_id else None,
        ConversationId(row.conversation_id),
        LeadId(row.lead_id) if row.lead_id else None,
        row.reason_code,
        row.priority,
        row.status,
        row.summary,
        dict(row.context),
        row.response_due_at,
        row.assignee_id,
    )


async def _schema_row(
    session: AsyncSession, tenant_id: TenantId, schema_id: UUID
) -> QualificationSchemaRow:
    row = await session.scalar(
        select(QualificationSchemaRow).where(
            QualificationSchemaRow.tenant_id == tenant_id.value,
            QualificationSchemaRow.id == schema_id,
        )
    )
    if row is None:
        raise ValueError("Qualification schema is unavailable")
    return row


async def _locked_session(
    session: AsyncSession,
    identity: TelegramIdentity,
    session_id: QualificationSessionId,
) -> tuple[QualificationSessionRow, QualificationSchema]:
    row = await session.scalar(
        select(QualificationSessionRow)
        .where(
            QualificationSessionRow.tenant_id == identity.tenant_id.value,
            QualificationSessionRow.customer_id == identity.customer_id.value,
            QualificationSessionRow.conversation_id == identity.conversation_id.value,
            QualificationSessionRow.id == session_id.value,
        )
        .with_for_update()
    )
    if row is None:
        raise ValueError("Qualification session is unavailable")
    schema = _schema(await _schema_row(session, identity.tenant_id, row.schema_id))
    return row, schema


async def _is_duplicate(
    session: AsyncSession, tenant_id: TenantId, session_id: UUID, update_key: str
) -> bool:
    found = await session.scalar(
        select(QualificationSessionUpdateRow.session_id).where(
            QualificationSessionUpdateRow.tenant_id == tenant_id.value,
            QualificationSessionUpdateRow.update_key == update_key,
        )
    )
    if found is not None and found != session_id:
        raise ValueError("Qualification update belongs to another session")
    return found is not None


def _record_update(
    session: AsyncSession,
    tenant_id: TenantId,
    session_id: UUID,
    update_key: str,
    operation: str,
    now: datetime,
) -> None:
    session.add(
        QualificationSessionUpdateRow(
            id=uuid4(),
            tenant_id=tenant_id.value,
            session_id=session_id,
            update_key=update_key,
            operation=operation,
            processed_at=now,
        )
    )


def _event_id(tenant_id: TenantId, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"business-assistant:{tenant_id}:{key}")


def _outbox(
    session: AsyncSession,
    tenant_id: TenantId,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    key: str,
    payload: dict[str, Any],
    now: datetime,
) -> None:
    event_id = _event_id(tenant_id, key)
    session.add(
        OutboxEventRow(
            id=event_id,
            event_id=event_id,
            tenant_id=tenant_id.value,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_version=1,
            payload=payload,
            status="pending",
            attempts=0,
            available_at=now,
            occurred_at=now,
        )
    )


class SQLAlchemyQualificationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def published_schema(self, tenant_id: TenantId, code: str) -> QualificationSchema | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(QualificationSchemaRow).where(
                    QualificationSchemaRow.tenant_id == tenant_id.value,
                    QualificationSchemaRow.code == code,
                    QualificationSchemaRow.published.is_(True),
                    QualificationSchemaRow.active.is_(True),
                )
            )
        return _schema(row) if row else None

    async def schema(
        self, tenant_id: TenantId, schema_id: QualificationSchemaId
    ) -> QualificationSchema | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(QualificationSchemaRow).where(
                    QualificationSchemaRow.tenant_id == tenant_id.value,
                    QualificationSchemaRow.id == schema_id.value,
                )
            )
        return _schema(row) if row else None

    async def active_session(
        self, identity: TelegramIdentity, *, now: datetime
    ) -> QualificationSession | None:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(QualificationSessionRow)
                .where(
                    QualificationSessionRow.tenant_id == identity.tenant_id.value,
                    QualificationSessionRow.customer_id == identity.customer_id.value,
                    QualificationSessionRow.conversation_id == identity.conversation_id.value,
                    QualificationSessionRow.status.in_(
                        ("awaiting_consent", "in_progress", "reviewing")
                    ),
                )
                .with_for_update()
            )
            if row is None:
                return None
            schema = _schema(await _schema_row(session, identity.tenant_id, row.schema_id))
            if row.expires_at <= now:
                row.status = QualificationSessionStatus.EXPIRED.value
                row.current_field_key = None
                conversation = await session.get(ConversationRow, identity.conversation_id.value)
                if conversation is not None:
                    conversation.active_workflow = None
                return None
            return _session(row, schema)

    async def start(
        self, identity: TelegramIdentity, schema: QualificationSchema, *, now: datetime
    ) -> QualificationSession:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"qualification:{identity.tenant_id}:{identity.conversation_id}"},
            )
            existing = await session.scalar(
                select(QualificationSessionRow).where(
                    QualificationSessionRow.tenant_id == identity.tenant_id.value,
                    QualificationSessionRow.customer_id == identity.customer_id.value,
                    QualificationSessionRow.conversation_id == identity.conversation_id.value,
                    QualificationSessionRow.status.in_(
                        ("awaiting_consent", "in_progress", "reviewing")
                    ),
                )
            )
            if existing is not None and existing.expires_at > now:
                existing_schema = _schema(
                    await _schema_row(session, identity.tenant_id, existing.schema_id)
                )
                return _session(existing, existing_schema)
            if existing is not None:
                existing.status = QualificationSessionStatus.EXPIRED.value
                existing.current_field_key = None
            row = QualificationSessionRow(
                id=uuid4(),
                tenant_id=identity.tenant_id.value,
                customer_id=identity.customer_id.value,
                conversation_id=identity.conversation_id.value,
                schema_id=schema.id.value,
                schema_code=schema.code,
                schema_version=schema.version,
                status=QualificationSessionStatus.AWAITING_CONSENT.value,
                answers={},
                current_field_key=None,
                expires_at=now + schema.session_ttl,
                revision=1,
            )
            session.add(row)
            conversation = await session.get(ConversationRow, identity.conversation_id.value)
            if (
                conversation is None
                or conversation.tenant_id != identity.tenant_id.value
                or conversation.status != "active_bot"
            ):
                raise ValueError("Qualification conversation is unavailable")
            conversation.active_workflow = f"qualification:{row.id}"
            await session.flush()
            return _session(row, schema)

    async def decide_consent(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        decision: ConsentDecision,
        *,
        now: datetime,
        update_key: str,
    ) -> QualificationSession:
        async with self._session_factory() as session, session.begin():
            row, schema = await _locked_session(session, identity, session_id)
            if await _is_duplicate(session, identity.tenant_id, row.id, update_key):
                return _session(row, schema)
            if row.status != QualificationSessionStatus.AWAITING_CONSENT.value:
                raise ValueError("Qualification consent was already decided")
            row.consent_decision = decision.value
            row.consent_at = now
            row.status = (
                QualificationSessionStatus.IN_PROGRESS.value
                if decision is ConsentDecision.ACCEPTED
                else QualificationSessionStatus.DECLINED.value
            )
            first_required = next_missing_field(schema, {})
            row.current_field_key = (
                first_required.key
                if decision is ConsentDecision.ACCEPTED and first_required is not None
                else None
            )
            if decision is ConsentDecision.ACCEPTED and first_required is None:
                row.status = QualificationSessionStatus.REVIEWING.value
            session.add(
                QualificationConsentRow(
                    id=uuid4(),
                    tenant_id=identity.tenant_id.value,
                    session_id=row.id,
                    customer_id=identity.customer_id.value,
                    decision=decision.value,
                    consent_version=schema.consent_version,
                    purpose=schema.consent_purpose,
                    decided_at=now,
                )
            )
            if decision is ConsentDecision.DECLINED:
                conversation = await session.get(ConversationRow, identity.conversation_id.value)
                if conversation is not None:
                    conversation.active_workflow = None
            _record_update(session, identity.tenant_id, row.id, update_key, "consent", now)
            await session.flush()
            return _session(row, schema)

    async def record_answer(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        field_key: str,
        answer: Answer,
        *,
        now: datetime,
        update_key: str,
    ) -> QualificationSession:
        async with self._session_factory() as session, session.begin():
            row, schema = await _locked_session(session, identity, session_id)
            if await _is_duplicate(session, identity.tenant_id, row.id, update_key):
                return _session(row, schema)
            if (
                row.status != QualificationSessionStatus.IN_PROGRESS.value
                or row.current_field_key != field_key
            ):
                raise ValueError("Qualification answer is not expected")
            answers = dict(row.answers)
            answers[field_key] = _stored_answer(answer)
            row.answers = answers
            typed = _session(row, schema).answers
            missing = next_missing_field(schema, typed)
            row.current_field_key = missing.key if missing else None
            row.status = (
                QualificationSessionStatus.IN_PROGRESS.value
                if missing
                else QualificationSessionStatus.REVIEWING.value
            )
            _record_update(session, identity.tenant_id, row.id, update_key, "answer", now)
            await session.flush()
            return _session(row, schema)

    async def review(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        *,
        now: datetime,
        edit_field_key: str | None = None,
    ) -> QualificationSession:
        _ = now
        async with self._session_factory() as session, session.begin():
            row, schema = await _locked_session(session, identity, session_id)
            if edit_field_key is not None:
                if edit_field_key not in {field.key for field in schema.fields}:
                    raise ValueError("Qualification field is unavailable")
                row.status = QualificationSessionStatus.IN_PROGRESS.value
                row.current_field_key = edit_field_key
            elif next_missing_field(schema, _session(row, schema).answers) is None:
                row.status = QualificationSessionStatus.REVIEWING.value
                row.current_field_key = None
            await session.flush()
            return _session(row, schema)

    async def complete(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        lead: Lead,
        score: ScoreResult,
        trigger: TriggerResult | None,
        *,
        now: datetime,
        update_key: str,
    ) -> QualificationSession:
        async with self._session_factory() as session, session.begin():
            row, schema = await _locked_session(session, identity, session_id)
            if await _is_duplicate(session, identity.tenant_id, row.id, update_key):
                return _session(row, schema)
            if row.status == QualificationSessionStatus.COMPLETED.value:
                return _session(row, schema)
            if row.status != QualificationSessionStatus.REVIEWING.value:
                raise ValueError("Qualification is not ready for submission")
            lead_row = await session.scalar(
                select(LeadRow)
                .where(
                    LeadRow.tenant_id == identity.tenant_id.value,
                    LeadRow.customer_id == identity.customer_id.value,
                    LeadRow.conversation_id == identity.conversation_id.value,
                    LeadRow.schema_code == schema.code,
                    LeadRow.status.in_(("new", "qualifying", "qualified", "unqualified")),
                )
                .order_by(LeadRow.updated_at.desc())
                .limit(1)
                .with_for_update()
            )
            replacement = lead_to_row(lead)
            if lead_row is None:
                lead_row = replacement
                session.add(lead_row)
                await session.flush([lead_row])
            else:
                for attribute in (
                    "schema_version",
                    "source",
                    "answers",
                    "status",
                    "score",
                    "priority",
                    "score_explanation",
                    "consent_at",
                    "qualification_snapshot",
                    "qualified_at",
                ):
                    setattr(lead_row, attribute, getattr(replacement, attribute))
            row.status = QualificationSessionStatus.COMPLETED.value
            row.lead_id = lead_row.id
            conversation = await session.get(ConversationRow, identity.conversation_id.value)
            if conversation is None:
                raise ValueError("Qualification conversation is unavailable")
            conversation.active_workflow = None
            _outbox(
                session,
                identity.tenant_id,
                "lead",
                lead_row.id,
                "lead.qualified",
                f"lead-qualified:{row.id}",
                {"lead_id": str(lead_row.id), "score": score.score, "grade": score.grade},
                now,
            )
            if trigger is not None:
                schedule = await _load_schedule(session, identity.tenant_id)
                due = business_due_at(
                    schedule, now, timedelta(minutes=schema.handoff_response_minutes)
                )
                handoff_id = uuid4()
                handoff = HandoffCaseRow(
                    id=handoff_id,
                    tenant_id=identity.tenant_id.value,
                    customer_id=identity.customer_id.value,
                    conversation_id=identity.conversation_id.value,
                    lead_id=lead_row.id,
                    reason_code=trigger.reason_code,
                    priority=trigger.priority,
                    status=HandoffStatus.QUEUED.value,
                    summary=f"Qualification triggered escalation: {trigger.reason_code}.",
                    context={
                        "matched_rules": list(trigger.matched_rules),
                        "timezone": schedule.timezone,
                    },
                    response_due_at=due,
                    idempotency_key=f"qualification:{row.id}:{trigger.reason_code}",
                )
                session.add(handoff)
                conversation.status = "handoff_queued"
                _outbox(
                    session,
                    identity.tenant_id,
                    "handoff",
                    handoff_id,
                    "handoff.queued",
                    f"handoff-qualified:{row.id}",
                    {
                        "handoff_id": str(handoff_id),
                        "reason_code": trigger.reason_code,
                        "priority": trigger.priority,
                    },
                    now,
                )
            _record_update(session, identity.tenant_id, row.id, update_key, "complete", now)
            await session.flush()
            return _session(row, schema)

    async def cancel(self, identity: TelegramIdentity, *, now: datetime) -> bool:
        _ = now
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(QualificationSessionRow)
                .where(
                    QualificationSessionRow.tenant_id == identity.tenant_id.value,
                    QualificationSessionRow.customer_id == identity.customer_id.value,
                    QualificationSessionRow.conversation_id == identity.conversation_id.value,
                    QualificationSessionRow.status.in_(
                        ("awaiting_consent", "in_progress", "reviewing")
                    ),
                )
                .with_for_update()
            )
            if row is None:
                return False
            row.status = QualificationSessionStatus.CANCELLED.value
            row.current_field_key = None
            conversation = await session.get(ConversationRow, identity.conversation_id.value)
            if conversation is not None:
                conversation.active_workflow = None
            return True

    async def get_lead(self, tenant_id: TenantId, lead_id: LeadId) -> Lead | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(LeadRow).where(
                    LeadRow.tenant_id == tenant_id.value, LeadRow.id == lead_id.value
                )
            )
        return lead_from_row(row) if row else None

    async def list_schemas(self, tenant_id: TenantId) -> tuple[QualificationSchema, ...]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(QualificationSchemaRow)
                        .where(QualificationSchemaRow.tenant_id == tenant_id.value)
                        .order_by(QualificationSchemaRow.code, QualificationSchemaRow.version)
                    )
                ).all()
            )
        return tuple(_schema(row) for row in rows)

    async def add_schema(self, schema: QualificationSchema) -> QualificationSchema:
        async with self._session_factory() as session, session.begin():
            row = QualificationSchemaRow(
                id=schema.id.value,
                tenant_id=schema.tenant_id.value,
                code=schema.code,
                version=schema.version,
                title=schema.title,
                consent_version=schema.consent_version,
                consent_purpose=schema.consent_purpose,
                definition=schema_definition(schema),
                grade_bands=[
                    {"minimum_score": band.minimum_score, "grade": band.grade}
                    for band in schema.grade_bands
                ],
                session_ttl_minutes=int(schema.session_ttl.total_seconds() // 60),
                handoff_response_minutes=schema.handoff_response_minutes,
                published=False,
                active=schema.active,
                config_version=1,
            )
            session.add(row)
            await session.flush()
            return _schema(row)

    async def publish_schema(
        self, tenant_id: TenantId, schema_id: QualificationSchemaId
    ) -> QualificationSchema:
        async with self._session_factory() as session, session.begin():
            target = await session.scalar(
                select(QualificationSchemaRow)
                .where(
                    QualificationSchemaRow.tenant_id == tenant_id.value,
                    QualificationSchemaRow.id == schema_id.value,
                )
                .with_for_update()
            )
            if target is None or not target.active:
                raise ValueError("Qualification schema is unavailable")
            current = list(
                (
                    await session.scalars(
                        select(QualificationSchemaRow)
                        .where(
                            QualificationSchemaRow.tenant_id == tenant_id.value,
                            QualificationSchemaRow.code == target.code,
                            QualificationSchemaRow.published.is_(True),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for row in current:
                row.published = False
            await session.flush()
            target.published = True
            await session.flush()
            return _schema(target)


async def _load_schedule(session: AsyncSession, tenant_id: TenantId) -> BusinessSchedule:
    profile = await session.get(TenantPublicProfileRow, tenant_id.value)
    if profile is None:
        raise ValueError("Handoff schedule is unavailable")
    row = await session.scalar(
        select(BusinessScheduleRow).where(
            BusinessScheduleRow.tenant_id == tenant_id.value,
            BusinessScheduleRow.id == profile.schedule_id,
        )
    )
    if row is None:
        raise ValueError("Handoff schedule is unavailable")
    intervals = list(
        (
            await session.scalars(
                select(ScheduleIntervalRow).where(
                    ScheduleIntervalRow.tenant_id == tenant_id.value,
                    ScheduleIntervalRow.schedule_id == row.id,
                )
            )
        ).all()
    )
    overrides = list(
        (
            await session.scalars(
                select(ScheduleOverrideRow).where(
                    ScheduleOverrideRow.tenant_id == tenant_id.value,
                    ScheduleOverrideRow.schedule_id == row.id,
                )
            )
        ).all()
    )
    return schedule_from_rows(row, intervals, overrides)


class SQLAlchemyHandoffStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def schedule(self, tenant_id: TenantId) -> BusinessSchedule | None:
        async with self._session_factory() as session:
            return await _load_schedule(session, tenant_id)

    async def active(self, identity: TelegramIdentity) -> HandoffView | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(HandoffCaseRow)
                .where(
                    HandoffCaseRow.tenant_id == identity.tenant_id.value,
                    HandoffCaseRow.conversation_id == identity.conversation_id.value,
                    HandoffCaseRow.status.in_(("queued", "claimed", "reopened")),
                )
                .order_by(HandoffCaseRow.created_at.desc())
            )
        return _handoff_view(row) if row else None

    async def create_or_get(
        self,
        identity: TelegramIdentity,
        *,
        reason_code: str,
        priority: str,
        summary: str,
        context: dict[str, Any],
        lead_id: LeadId | None,
        response_due_at: datetime,
        idempotency_key: str,
        now: datetime,
    ) -> HandoffView:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"handoff:{identity.tenant_id}:{identity.conversation_id}"},
            )
            existing = await session.scalar(
                select(HandoffCaseRow).where(
                    HandoffCaseRow.tenant_id == identity.tenant_id.value,
                    HandoffCaseRow.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return _handoff_view(existing)
            existing = await session.scalar(
                select(HandoffCaseRow).where(
                    HandoffCaseRow.tenant_id == identity.tenant_id.value,
                    HandoffCaseRow.conversation_id == identity.conversation_id.value,
                    HandoffCaseRow.status.in_(("queued", "claimed", "reopened")),
                )
            )
            if existing is not None:
                return _handoff_view(existing)
            row = HandoffCaseRow(
                id=uuid4(),
                tenant_id=identity.tenant_id.value,
                customer_id=identity.customer_id.value,
                conversation_id=identity.conversation_id.value,
                lead_id=lead_id.value if lead_id else None,
                reason_code=reason_code,
                priority=priority,
                status=HandoffStatus.QUEUED.value,
                summary=summary,
                context=context,
                response_due_at=response_due_at,
                idempotency_key=idempotency_key,
            )
            session.add(row)
            conversation = await session.get(ConversationRow, identity.conversation_id.value)
            if conversation is None or conversation.tenant_id != identity.tenant_id.value:
                raise ValueError("Handoff conversation is unavailable")
            conversation.status = "handoff_queued"
            conversation.active_workflow = None
            _outbox(
                session,
                identity.tenant_id,
                "handoff",
                row.id,
                "handoff.queued",
                f"handoff:{idempotency_key}",
                {"handoff_id": str(row.id), "reason_code": reason_code, "priority": priority},
                now,
            )
            await session.flush()
            return _handoff_view(row)

    async def list_open(self, tenant_id: TenantId, *, limit: int) -> Sequence[HandoffView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(HandoffCaseRow)
                        .where(
                            HandoffCaseRow.tenant_id == tenant_id.value,
                            HandoffCaseRow.status.in_(("queued", "claimed", "reopened")),
                        )
                        .order_by(HandoffCaseRow.response_due_at, HandoffCaseRow.id)
                        .limit(limit)
                    )
                ).all()
            )
        return [_handoff_view(row) for row in rows]

    async def transition(
        self,
        tenant_id: TenantId,
        handoff_id: HandoffId,
        *,
        action: str,
        actor_id: str,
        now: datetime,
    ) -> HandoffView:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(HandoffCaseRow)
                .where(
                    HandoffCaseRow.tenant_id == tenant_id.value,
                    HandoffCaseRow.id == handoff_id.value,
                )
                .with_for_update()
            )
            if row is None:
                raise ValueError("Handoff was not found")
            case = handoff_from_row(row)
            conversation = await session.get(ConversationRow, row.conversation_id)
            if conversation is None or conversation.tenant_id != tenant_id.value:
                raise ValueError("Handoff conversation is unavailable")
            if action == "claim":
                if case.status is HandoffStatus.REOPENED:
                    case.transition_to(HandoffStatus.QUEUED)
                case.transition_to(HandoffStatus.CLAIMED, assignee_id=actor_id)
                conversation.status = "human_active"
            elif action == "resolve":
                case.transition_to(HandoffStatus.RESOLVED)
            elif action == "reopen":
                case.transition_to(HandoffStatus.REOPENED)
                conversation.status = "handoff_queued"
            elif action == "return_to_bot":
                if case.status is not HandoffStatus.RESOLVED:
                    raise ValueError("Only a resolved handoff can return control")
                conversation.status = "active_bot"
            replacement = handoff_to_row(case)
            row.status = replacement.status
            row.assignee_id = replacement.assignee_id
            session.add(
                AuditEventRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    actor_type="staff",
                    actor_id=actor_id,
                    action=f"handoff.{action}",
                    target_type="handoff",
                    target_id=str(handoff_id),
                    safe_diff={"status": row.status},
                    correlation_id=_event_id(
                        tenant_id, f"audit:{handoff_id}:{action}:{now.isoformat()}"
                    ),
                    occurred_at=now,
                )
            )
            await session.flush()
            return _handoff_view(row)
