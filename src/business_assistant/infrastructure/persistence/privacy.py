"""Tenant-scoped PostgreSQL privacy, anonymization, and retention adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import case, delete, exists, func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import PrivacyError
from business_assistant.application.privacy import PrivacyResult, RetentionPolicy
from business_assistant.domain.shared import CustomerId, TenantId

from .sqlalchemy.models import (
    AIOperationRow,
    AuditEventRow,
    BookingDraftRow,
    BookingRow,
    ChannelIdentityRow,
    ConversationRow,
    CustomerRow,
    HandoffCaseRow,
    KnowledgeChunkRow,
    KnowledgeDocumentRow,
    LeadRow,
    MessageRow,
    PrivacyActionRow,
    QualificationSessionRow,
    RetentionPolicyRow,
    SlotHoldRow,
    TelegramUpdateRow,
    TenantRow,
)


class SQLAlchemyPrivacyStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_policy(self, tenant_id: TenantId) -> RetentionPolicy | None:
        async with self._session_factory() as session:
            row = await session.get(RetentionPolicyRow, tenant_id.value)
            return _policy(row) if row is not None else None

    async def run_scheduled_retention(self, *, at: datetime, limit: int = 100) -> int:
        """Execute only policies whose owner explicitly opted into automation."""
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(RetentionPolicyRow)
                        .join(TenantRow, TenantRow.id == RetentionPolicyRow.tenant_id)
                        .where(
                            RetentionPolicyRow.automatic_execution_enabled.is_(True),
                            TenantRow.status == "active",
                        )
                        .order_by(RetentionPolicyRow.tenant_id)
                        .limit(limit)
                    )
                ).all()
            )
        completed = 0
        for row in rows:
            policy = _policy(row)
            key = f"scheduled-retention:{at.date().isoformat()}:v{policy.version}"
            await self.run_retention(
                policy.tenant_id,
                policy,
                dry_run=False,
                idempotency_key=key,
                actor_id="phase10-worker",
                at=at,
            )
            completed += 1
        return completed

    async def update_policy(
        self,
        policy: RetentionPolicy,
        *,
        expected_version: int,
        actor_id: str,
        at: datetime,
    ) -> RetentionPolicy:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(RetentionPolicyRow)
                .where(
                    RetentionPolicyRow.tenant_id == policy.tenant_id.value,
                    RetentionPolicyRow.version == expected_version,
                )
                .with_for_update()
            )
            if row is None:
                raise PrivacyError(
                    "Retention policy version is stale or missing",
                    code="privacy.policy_conflict",
                )
            before = _policy_values(_policy(row))
            row.operational_metadata_days = policy.operational_metadata_days
            row.message_content_days = policy.message_content_days
            row.customer_contact_days = policy.customer_contact_days
            row.workflow_records_days = policy.workflow_records_days
            row.knowledge_archive_days = policy.knowledge_archive_days
            row.ai_telemetry_days = policy.ai_telemetry_days
            row.automatic_execution_enabled = policy.automatic_execution_enabled
            row.version = policy.version
            row.updated_at = at
            session.add(
                _audit(
                    policy.tenant_id,
                    actor_id,
                    "privacy.retention_policy_updated",
                    "retention_policy",
                    str(policy.tenant_id),
                    {"before": before, "after": _policy_values(policy)},
                    at,
                )
            )
            await session.flush()
            return _policy(row)

    async def anonymize_customer(
        self,
        tenant_id: TenantId,
        customer_id: CustomerId,
        *,
        idempotency_key: str,
        reason_code: str,
        actor_id: str,
        at: datetime,
    ) -> PrivacyResult:
        async with self._session_factory() as session, session.begin():
            await _privacy_lock(session, tenant_id, idempotency_key)
            replay = await _replay(
                session,
                tenant_id,
                idempotency_key,
                action_type="customer_anonymization",
                target_id=str(customer_id),
            )
            if replay is not None:
                return replay
            policy = await session.get(RetentionPolicyRow, tenant_id.value)
            if policy is None:
                raise PrivacyError(
                    "Retention policy was not found", code="privacy.policy_not_found"
                )
            customer = await session.scalar(
                select(CustomerRow)
                .where(
                    CustomerRow.tenant_id == tenant_id.value,
                    CustomerRow.id == customer_id.value,
                )
                .with_for_update()
            )
            if customer is None:
                raise PrivacyError("Customer was not found", code="privacy.customer_not_found")
            counts = await _anonymize_customer_rows(session, tenant_id, customer, at)
            action = _privacy_action(
                tenant_id,
                "customer_anonymization",
                "customer",
                str(customer_id),
                idempotency_key,
                reason_code,
                policy.version,
                counts,
                actor_id,
                at,
            )
            session.add(action)
            session.add(
                _audit(
                    tenant_id,
                    actor_id,
                    "privacy.customer_anonymized",
                    "customer",
                    str(customer_id),
                    {"reason_code": reason_code, "action_id": str(action.id)},
                    at,
                )
            )
            await session.flush()
            return PrivacyResult(str(action.id), action.action_type, False, policy.version, counts)

    async def run_retention(
        self,
        tenant_id: TenantId,
        policy: RetentionPolicy,
        *,
        dry_run: bool,
        idempotency_key: str | None,
        actor_id: str,
        at: datetime,
    ) -> PrivacyResult:
        async with self._session_factory() as session, session.begin():
            if not dry_run:
                assert idempotency_key is not None
                await _privacy_lock(session, tenant_id, idempotency_key)
                replay = await _replay(
                    session,
                    tenant_id,
                    idempotency_key,
                    action_type="retention_execution",
                    target_id=None,
                )
                if replay is not None:
                    return replay
            execution_key = idempotency_key
            stored = await session.scalar(
                select(RetentionPolicyRow)
                .where(
                    RetentionPolicyRow.tenant_id == tenant_id.value,
                    RetentionPolicyRow.version == policy.version,
                )
                .with_for_update()
            )
            if stored is None:
                raise PrivacyError(
                    "Retention policy changed before execution",
                    code="privacy.policy_conflict",
                )
            counts = await _retention_counts(session, tenant_id, policy, at)
            if dry_run:
                await session.rollback()
                return PrivacyResult(None, "retention_preview", True, policy.version, counts)
            applied = await _apply_retention(session, tenant_id, policy, at)
            action = _privacy_action(
                tenant_id,
                "retention_execution",
                None,
                None,
                cast(str, execution_key),
                "scheduled_retention",
                policy.version,
                applied,
                actor_id,
                at,
            )
            session.add(action)
            session.add(
                _audit(
                    tenant_id,
                    actor_id,
                    "privacy.retention_executed",
                    "retention_policy",
                    str(tenant_id),
                    {"policy_version": policy.version, "action_id": str(action.id)},
                    at,
                )
            )
            await session.flush()
            return PrivacyResult(str(action.id), action.action_type, False, policy.version, applied)


def _policy(row: RetentionPolicyRow) -> RetentionPolicy:
    return RetentionPolicy(
        TenantId(row.tenant_id),
        row.version,
        row.operational_metadata_days,
        row.message_content_days,
        row.customer_contact_days,
        row.workflow_records_days,
        row.knowledge_archive_days,
        row.ai_telemetry_days,
        row.automatic_execution_enabled,
    )


def _policy_values(policy: RetentionPolicy) -> dict[str, int | bool]:
    return {
        "version": policy.version,
        "operational_metadata_days": policy.operational_metadata_days,
        "message_content_days": policy.message_content_days,
        "customer_contact_days": policy.customer_contact_days,
        "workflow_records_days": policy.workflow_records_days,
        "knowledge_archive_days": policy.knowledge_archive_days,
        "ai_telemetry_days": policy.ai_telemetry_days,
        "automatic_execution_enabled": policy.automatic_execution_enabled,
    }


async def _privacy_lock(session: AsyncSession, tenant_id: TenantId, key: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"privacy:{tenant_id}:{key}"},
    )


async def _replay(
    session: AsyncSession,
    tenant_id: TenantId,
    key: str,
    *,
    action_type: str,
    target_id: str | None,
) -> PrivacyResult | None:
    row = await session.scalar(
        select(PrivacyActionRow).where(
            PrivacyActionRow.tenant_id == tenant_id.value,
            PrivacyActionRow.idempotency_key == key,
        )
    )
    if row is None:
        return None
    if row.action_type != action_type or row.target_id != target_id:
        raise PrivacyError(
            "Privacy idempotency key is already used for another operation",
            code="privacy.idempotency_conflict",
        )
    return PrivacyResult(
        str(row.id), row.action_type, False, row.policy_version, row.result_counts, True
    )


async def _anonymize_customer_rows(
    session: AsyncSession, tenant_id: TenantId, customer: CustomerRow, at: datetime
) -> dict[str, int]:
    customer.display_name = None
    customer.phone_raw = None
    customer.phone_e164 = None
    customer.phone_verified = False
    customer.email = None
    customer.contact_consent_at = None
    customer.status = "anonymized"
    customer.updated_at = at
    identities = (
        await session.scalars(
            select(ChannelIdentityRow).where(
                ChannelIdentityRow.tenant_id == tenant_id.value,
                ChannelIdentityRow.customer_id == customer.id,
            )
        )
    ).all()
    for identity in identities:
        replacement = f"anonymized:{identity.id}"
        identity.external_user_id = replacement
        identity.external_chat_id = replacement
    conversation_ids = tuple(
        await session.scalars(
            select(ConversationRow.id).where(
                ConversationRow.tenant_id == tenant_id.value,
                ConversationRow.customer_id == customer.id,
            )
        )
    )
    counts: dict[str, int] = {"customers_anonymized": 1, "identities_anonymized": len(identities)}
    counts["conversations_closed"] = await _update_count(
        session,
        update(ConversationRow)
        .where(
            ConversationRow.tenant_id == tenant_id.value,
            ConversationRow.customer_id == customer.id,
        )
        .values(status="closed", active_workflow=None, updated_at=at),
    )
    if conversation_ids:
        counts["messages_deleted"] = await _delete_count(
            session,
            delete(MessageRow).where(
                MessageRow.tenant_id == tenant_id.value,
                MessageRow.conversation_id.in_(conversation_ids),
            ),
        )
    else:
        counts["messages_deleted"] = 0
    counts["booking_drafts_anonymized"] = await _update_count(
        session,
        update(BookingDraftRow)
        .where(
            BookingDraftRow.tenant_id == tenant_id.value,
            BookingDraftRow.customer_id == customer.id,
        )
        .values(
            customer_name=None,
            customer_phone=None,
            customer_note=None,
            status=case(
                (BookingDraftRow.status == "active", "cancelled"),
                else_=BookingDraftRow.status,
            ),
            updated_at=at,
        ),
    )
    counts["slot_holds_released"] = await _update_count(
        session,
        update(SlotHoldRow)
        .where(
            SlotHoldRow.tenant_id == tenant_id.value,
            SlotHoldRow.customer_id == customer.id,
            SlotHoldRow.status == "active",
        )
        .values(status="released", updated_at=at),
    )
    counts["bookings_anonymized"] = await _update_count(
        session,
        update(BookingRow)
        .where(BookingRow.tenant_id == tenant_id.value, BookingRow.customer_id == customer.id)
        .values(customer_snapshot={}, notes=None, updated_at=at),
    )
    counts["leads_anonymized"] = await _update_count(
        session,
        update(LeadRow)
        .where(LeadRow.tenant_id == tenant_id.value, LeadRow.customer_id == customer.id)
        .values(answers={}, qualification_snapshot=None, updated_at=at),
    )
    counts["qualification_sessions_anonymized"] = await _update_count(
        session,
        update(QualificationSessionRow)
        .where(
            QualificationSessionRow.tenant_id == tenant_id.value,
            QualificationSessionRow.customer_id == customer.id,
        )
        .values(
            answers={},
            current_field_key=None,
            status=case(
                (
                    QualificationSessionRow.status.in_(
                        ("awaiting_consent", "in_progress", "reviewing")
                    ),
                    "cancelled",
                ),
                else_=QualificationSessionRow.status,
            ),
            updated_at=at,
        ),
    )
    counts["handoffs_anonymized"] = await _update_count(
        session,
        update(HandoffCaseRow)
        .where(
            HandoffCaseRow.tenant_id == tenant_id.value,
            HandoffCaseRow.customer_id == customer.id,
        )
        .values(
            summary="Customer data removed by privacy workflow.",
            context={},
            status=case(
                (HandoffCaseRow.status.in_(("queued", "claimed", "reopened")), "cancelled"),
                else_=HandoffCaseRow.status,
            ),
            updated_at=at,
        ),
    )
    return counts


async def _retention_counts(
    session: AsyncSession, tenant_id: TenantId, policy: RetentionPolicy, at: datetime
) -> dict[str, int]:
    operational_cutoff = at - timedelta(days=policy.operational_metadata_days)
    message_cutoff = at - timedelta(days=policy.message_content_days)
    workflow_cutoff = at - timedelta(days=policy.workflow_records_days)
    knowledge_cutoff = at - timedelta(days=policy.knowledge_archive_days)
    ai_cutoff = at - timedelta(days=policy.ai_telemetry_days)
    customer_ids = await _eligible_customer_ids(
        session, tenant_id, at - timedelta(days=policy.customer_contact_days)
    )
    workflow_conditions = _workflow_conditions(tenant_id, workflow_cutoff)
    return {
        "operational_metadata_deleted": await _count(
            session,
            TelegramUpdateRow,
            TelegramUpdateRow.tenant_id == tenant_id.value,
            TelegramUpdateRow.status.in_(("completed", "failed")),
            TelegramUpdateRow.created_at < operational_cutoff,
        ),
        "messages_deleted": await _count(
            session,
            MessageRow,
            MessageRow.tenant_id == tenant_id.value,
            MessageRow.created_at < message_cutoff,
        ),
        "customers_anonymized": len(customer_ids),
        "workflow_records_anonymized": sum(
            [await _count(session, model, *conditions) for model, conditions in workflow_conditions]
        ),
        "knowledge_documents_deleted": await _count(
            session,
            KnowledgeDocumentRow,
            KnowledgeDocumentRow.tenant_id == tenant_id.value,
            KnowledgeDocumentRow.status == "archived",
            KnowledgeDocumentRow.updated_at < knowledge_cutoff,
        ),
        "ai_telemetry_deleted": await _count(
            session,
            AIOperationRow,
            AIOperationRow.tenant_id == tenant_id.value,
            AIOperationRow.created_at < ai_cutoff,
        ),
        "audit_events_preserved": await _count(
            session, AuditEventRow, AuditEventRow.tenant_id == tenant_id.value
        ),
    }


async def _apply_retention(
    session: AsyncSession, tenant_id: TenantId, policy: RetentionPolicy, at: datetime
) -> dict[str, int]:
    expected = await _retention_counts(session, tenant_id, policy, at)
    customer_ids = await _eligible_customer_ids(
        session, tenant_id, at - timedelta(days=policy.customer_contact_days)
    )
    for customer_id in customer_ids:
        customer = await session.scalar(
            select(CustomerRow)
            .where(CustomerRow.tenant_id == tenant_id.value, CustomerRow.id == customer_id)
            .with_for_update()
        )
        if customer is not None:
            await _anonymize_customer_rows(session, tenant_id, customer, at)
    await _delete_count(
        session,
        delete(TelegramUpdateRow).where(
            TelegramUpdateRow.tenant_id == tenant_id.value,
            TelegramUpdateRow.status.in_(("completed", "failed")),
            TelegramUpdateRow.created_at < at - timedelta(days=policy.operational_metadata_days),
        ),
    )
    await _delete_count(
        session,
        delete(MessageRow).where(
            MessageRow.tenant_id == tenant_id.value,
            MessageRow.created_at < at - timedelta(days=policy.message_content_days),
        ),
    )
    for model, conditions in _workflow_conditions(
        tenant_id, at - timedelta(days=policy.workflow_records_days)
    ):
        values: dict[str, Any]
        if model is BookingDraftRow:
            values = {"customer_name": None, "customer_phone": None, "customer_note": None}
        elif model is BookingRow:
            values = {"customer_snapshot": {}, "notes": None}
        elif model is LeadRow:
            values = {"answers": {}, "qualification_snapshot": None}
        elif model is QualificationSessionRow:
            values = {"answers": {}, "current_field_key": None}
        else:
            values = {"summary": "Personal content removed by retention policy.", "context": {}}
        await _update_count(session, update(model).where(*conditions).values(**values))
    document_ids = tuple(
        await session.scalars(
            select(KnowledgeDocumentRow.id).where(
                KnowledgeDocumentRow.tenant_id == tenant_id.value,
                KnowledgeDocumentRow.status == "archived",
                KnowledgeDocumentRow.updated_at
                < at - timedelta(days=policy.knowledge_archive_days),
            )
        )
    )
    if document_ids:
        await _delete_count(
            session,
            delete(KnowledgeChunkRow).where(
                KnowledgeChunkRow.tenant_id == tenant_id.value,
                KnowledgeChunkRow.document_id.in_(document_ids),
            ),
        )
        await _delete_count(
            session,
            delete(KnowledgeDocumentRow).where(
                KnowledgeDocumentRow.tenant_id == tenant_id.value,
                KnowledgeDocumentRow.id.in_(document_ids),
            ),
        )
    await _delete_count(
        session,
        delete(AIOperationRow).where(
            AIOperationRow.tenant_id == tenant_id.value,
            AIOperationRow.created_at < at - timedelta(days=policy.ai_telemetry_days),
        ),
    )
    return expected


def _workflow_conditions(
    tenant_id: TenantId, cutoff: datetime
) -> tuple[tuple[type[Any], tuple[Any, ...]], ...]:
    return (
        (
            BookingDraftRow,
            (
                BookingDraftRow.tenant_id == tenant_id.value,
                BookingDraftRow.status.in_(("cancelled", "expired", "confirmed")),
                BookingDraftRow.updated_at < cutoff,
                (
                    BookingDraftRow.customer_name.is_not(None)
                    | BookingDraftRow.customer_phone.is_not(None)
                    | BookingDraftRow.customer_note.is_not(None)
                ),
            ),
        ),
        (
            BookingRow,
            (
                BookingRow.tenant_id == tenant_id.value,
                BookingRow.status.in_(("completed", "cancelled", "no_show", "expired")),
                BookingRow.updated_at < cutoff,
                ((BookingRow.customer_snapshot != {}) | BookingRow.notes.is_not(None)),
            ),
        ),
        (
            LeadRow,
            (
                LeadRow.tenant_id == tenant_id.value,
                LeadRow.status.in_(("unqualified", "closed")),
                LeadRow.updated_at < cutoff,
                ((LeadRow.answers != {}) | LeadRow.qualification_snapshot.is_not(None)),
            ),
        ),
        (
            QualificationSessionRow,
            (
                QualificationSessionRow.tenant_id == tenant_id.value,
                QualificationSessionRow.status.in_(
                    ("completed", "declined", "cancelled", "expired")
                ),
                QualificationSessionRow.updated_at < cutoff,
                (
                    (QualificationSessionRow.answers != {})
                    | QualificationSessionRow.current_field_key.is_not(None)
                ),
            ),
        ),
        (
            HandoffCaseRow,
            (
                HandoffCaseRow.tenant_id == tenant_id.value,
                HandoffCaseRow.status.in_(("resolved", "cancelled")),
                HandoffCaseRow.updated_at < cutoff,
                (
                    (HandoffCaseRow.context != {})
                    | (HandoffCaseRow.summary != "Personal content removed by retention policy.")
                ),
            ),
        ),
    )


async def _eligible_customer_ids(
    session: AsyncSession, tenant_id: TenantId, cutoff: datetime
) -> tuple[UUID, ...]:
    active_conversation = exists(
        select(ConversationRow.id).where(
            ConversationRow.tenant_id == CustomerRow.tenant_id,
            ConversationRow.customer_id == CustomerRow.id,
            ConversationRow.status != "closed",
        )
    )
    active_booking = exists(
        select(BookingRow.id).where(
            BookingRow.tenant_id == CustomerRow.tenant_id,
            BookingRow.customer_id == CustomerRow.id,
            BookingRow.status.in_(("draft", "held", "confirmed", "reschedule_pending")),
        )
    )
    active_lead = exists(
        select(LeadRow.id).where(
            LeadRow.tenant_id == CustomerRow.tenant_id,
            LeadRow.customer_id == CustomerRow.id,
            LeadRow.status.in_(("new", "qualifying", "qualified", "contacted", "converted")),
        )
    )
    active_qualification = exists(
        select(QualificationSessionRow.id).where(
            QualificationSessionRow.tenant_id == CustomerRow.tenant_id,
            QualificationSessionRow.customer_id == CustomerRow.id,
            QualificationSessionRow.status.in_(("awaiting_consent", "in_progress", "reviewing")),
        )
    )
    active_handoff = exists(
        select(HandoffCaseRow.id).where(
            HandoffCaseRow.tenant_id == CustomerRow.tenant_id,
            HandoffCaseRow.customer_id == CustomerRow.id,
            HandoffCaseRow.status.in_(("queued", "claimed", "reopened")),
        )
    )
    return tuple(
        await session.scalars(
            select(CustomerRow.id).where(
                CustomerRow.tenant_id == tenant_id.value,
                CustomerRow.status != "anonymized",
                CustomerRow.updated_at < cutoff,
                ~active_conversation,
                ~active_booking,
                ~active_lead,
                ~active_qualification,
                ~active_handoff,
            )
        )
    )


async def _count(session: AsyncSession, model: type[Any], *conditions: Any) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    )


async def _update_count(session: AsyncSession, statement: Any) -> int:
    result = cast(CursorResult[Any], await session.execute(statement))
    return int(result.rowcount or 0)


async def _delete_count(session: AsyncSession, statement: Any) -> int:
    result = cast(CursorResult[Any], await session.execute(statement))
    return int(result.rowcount or 0)


def _privacy_action(
    tenant_id: TenantId,
    action_type: str,
    target_type: str | None,
    target_id: str | None,
    idempotency_key: str,
    reason_code: str,
    policy_version: int,
    counts: dict[str, int],
    actor_id: str,
    at: datetime,
) -> PrivacyActionRow:
    return PrivacyActionRow(
        id=uuid4(),
        tenant_id=tenant_id.value,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        idempotency_key=idempotency_key,
        reason_code=reason_code,
        policy_version=policy_version,
        status="completed",
        result_counts=counts,
        requested_by=actor_id,
        occurred_at=at,
    )


def _audit(
    tenant_id: TenantId,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    safe_diff: dict[str, Any],
    at: datetime,
) -> AuditEventRow:
    return AuditEventRow(
        id=uuid4(),
        tenant_id=tenant_id.value,
        actor_type="staff",
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        safe_diff=safe_diff,
        correlation_id=uuid4(),
        occurred_at=at,
    )
