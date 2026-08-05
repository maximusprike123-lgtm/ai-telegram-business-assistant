import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from business_assistant.application.common.errors import PrivacyError
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.privacy import PrivacyApplication
from business_assistant.domain.shared import CustomerId, TenantId
from business_assistant.infrastructure.persistence import SQLAlchemyPrivacyStore
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    AIOperationRow,
    AuditEventRow,
    ChannelIdentityRow,
    ConversationRow,
    CustomerRow,
    KnowledgeChunkRow,
    KnowledgeDocumentRow,
    MessageRow,
    PrivacyActionRow,
    RetentionPolicyRow,
    TelegramUpdateRow,
    TenantRow,
)

pytestmark = pytest.mark.postgresql
NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=1000)


class Clock:
    def now(self):
        return NOW


def tenant_row(tenant_id: TenantId, slug: str) -> TenantRow:
    return TenantRow(
        id=tenant_id.value,
        slug=slug,
        name=slug,
        timezone="UTC",
        default_locale="en",
        supported_locales=["en"],
        status="active",
        settings_version=1,
    )


def policy_row(tenant_id: TenantId) -> RetentionPolicyRow:
    return RetentionPolicyRow(
        tenant_id=tenant_id.value,
        version=1,
        operational_metadata_days=30,
        message_content_days=90,
        customer_contact_days=365,
        workflow_records_days=730,
        knowledge_archive_days=365,
        ai_telemetry_days=90,
    )


@pytest.mark.asyncio
async def test_customer_anonymization_is_atomic_idempotent_tenant_scoped_and_preserves_audit(
    database,
) -> None:
    _, factory = database
    tenant_a, tenant_b = TenantId.new(), TenantId.new()
    customer_a, customer_b = CustomerId.new(), CustomerId.new()
    identity_a, identity_b = uuid4(), uuid4()
    conversation_a, conversation_b = uuid4(), uuid4()
    original_audit = uuid4()
    async with factory() as session, session.begin():
        session.add_all([tenant_row(tenant_a, "privacy-a"), tenant_row(tenant_b, "privacy-b")])
        await session.flush()
        session.add_all([policy_row(tenant_a), policy_row(tenant_b)])
        session.add_all(
            [
                CustomerRow(
                    id=customer_a.value,
                    tenant_id=tenant_a.value,
                    display_name="Private Customer",
                    phone_raw="+15550100",
                    phone_e164="+15550100",
                    phone_verified=True,
                    email="private@example.test",
                    locale="en",
                    status="active",
                ),
                CustomerRow(
                    id=customer_b.value,
                    tenant_id=tenant_b.value,
                    display_name="Other Tenant",
                    phone_verified=False,
                    locale="en",
                    status="active",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ChannelIdentityRow(
                    id=identity_a,
                    tenant_id=tenant_a.value,
                    customer_id=customer_a.value,
                    channel="telegram",
                    external_user_id="111",
                    external_chat_id="111",
                ),
                ChannelIdentityRow(
                    id=identity_b,
                    tenant_id=tenant_b.value,
                    customer_id=customer_b.value,
                    channel="telegram",
                    external_user_id="222",
                    external_chat_id="222",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ConversationRow(
                    id=conversation_a,
                    tenant_id=tenant_a.value,
                    customer_id=customer_a.value,
                    channel_identity_id=identity_a,
                    status="active_bot",
                    locale="en",
                    active_workflow="qualification",
                    summary_version=0,
                ),
                ConversationRow(
                    id=conversation_b,
                    tenant_id=tenant_b.value,
                    customer_id=customer_b.value,
                    channel_identity_id=identity_b,
                    status="active_bot",
                    locale="en",
                    summary_version=0,
                ),
            ]
        )
        await session.flush()
        session.add(
            MessageRow(
                id=uuid4(),
                tenant_id=tenant_a.value,
                conversation_id=conversation_a,
                direction="inbound",
                channel="telegram",
                channel_account_id="42",
                external_update_id="1",
                content_type="text",
                redacted_text="private message",
                status="processed",
                correlation_id=uuid4(),
            )
        )
        session.add(
            AuditEventRow(
                id=original_audit,
                tenant_id=tenant_a.value,
                actor_type="staff",
                actor_id="operator",
                action="fixture.created",
                target_type="customer",
                target_id=str(customer_a),
                safe_diff={},
                correlation_id=uuid4(),
                occurred_at=OLD,
            )
        )

    application = PrivacyApplication(SQLAlchemyPrivacyStore(factory), Clock())
    owner = Principal("privacy-owner", tenant_a, Role.OWNER)
    policy = await application.get_policy(owner)
    updated_policy = await application.update_policy(
        owner,
        type(policy)(tenant_a, 2, 30, 60, 365, 730, 365, 90),
        expected_version=1,
    )
    assert updated_policy.version == 2 and updated_policy.message_content_days == 60
    with pytest.raises(PrivacyError, match="stale"):
        await application.update_policy(owner, updated_policy, expected_version=1)
    first, replay = await asyncio.gather(
        *(
            application.anonymize_customer(
                owner,
                customer_a,
                confirmed=True,
                idempotency_key="customer-erasure-1",
                reason_code="customer_request",
            )
            for _ in range(2)
        )
    )
    assert first.action_id == replay.action_id
    assert first.idempotent_replay is not replay.idempotent_replay
    with pytest.raises(PrivacyError, match="not found"):
        await application.anonymize_customer(
            owner,
            customer_b,
            confirmed=True,
            idempotency_key="cross-tenant-attempt",
            reason_code="customer_request",
        )

    async with factory() as session:
        anonymized = await session.get(CustomerRow, customer_a.value)
        untouched = await session.get(CustomerRow, customer_b.value)
        identity = await session.get(ChannelIdentityRow, identity_a)
        conversation = await session.get(ConversationRow, conversation_a)
        assert anonymized is not None and anonymized.status == "anonymized"
        assert anonymized.display_name is anonymized.phone_raw is anonymized.email is None
        assert untouched is not None and untouched.display_name == "Other Tenant"
        assert identity is not None and identity.external_user_id.startswith("anonymized:")
        assert conversation is not None and conversation.status == "closed"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.tenant_id == tenant_a.value)
            )
            == 0
        )
        assert await session.get(AuditEventRow, original_audit) is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PrivacyActionRow)
                .where(PrivacyActionRow.tenant_id == tenant_a.value)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_retention_preview_and_execution_delete_only_due_tenant_data_and_keep_audit(
    database,
) -> None:
    _, factory = database
    tenant_a, tenant_b = TenantId.new(), TenantId.new()
    customer_a, customer_b = CustomerId.new(), CustomerId.new()
    conversation_a, conversation_b = uuid4(), uuid4()
    document_id, chunk_id, audit_id = uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add_all([tenant_row(tenant_a, "retention-a"), tenant_row(tenant_b, "retention-b")])
        await session.flush()
        session.add_all([policy_row(tenant_a), policy_row(tenant_b)])
        session.add_all(
            [
                CustomerRow(
                    id=customer_a.value,
                    tenant_id=tenant_a.value,
                    phone_verified=False,
                    locale="en",
                    status="anonymized",
                ),
                CustomerRow(
                    id=customer_b.value,
                    tenant_id=tenant_b.value,
                    phone_verified=False,
                    locale="en",
                    status="anonymized",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ConversationRow(
                    id=conversation_a,
                    tenant_id=tenant_a.value,
                    customer_id=customer_a.value,
                    status="closed",
                    locale="en",
                    summary_version=0,
                ),
                ConversationRow(
                    id=conversation_b,
                    tenant_id=tenant_b.value,
                    customer_id=customer_b.value,
                    status="closed",
                    locale="en",
                    summary_version=0,
                ),
            ]
        )
        await session.flush()
        for tenant, conversation, suffix in (
            (tenant_a, conversation_a, "a"),
            (tenant_b, conversation_b, "b"),
        ):
            session.add(
                MessageRow(
                    id=uuid4(),
                    tenant_id=tenant.value,
                    conversation_id=conversation,
                    direction="inbound",
                    channel="telegram",
                    channel_account_id="42",
                    external_update_id=suffix,
                    content_type="text",
                    redacted_text="old content",
                    status="processed",
                    correlation_id=uuid4(),
                    created_at=OLD,
                )
            )
            session.add(
                TelegramUpdateRow(
                    id=uuid4(),
                    tenant_id=tenant.value,
                    bot_id=42,
                    update_id=1 if tenant == tenant_a else 2,
                    status="completed",
                    attempts=1,
                    claimed_at=OLD,
                    completed_at=OLD,
                    created_at=OLD,
                    updated_at=OLD,
                )
            )
            session.add(
                AIOperationRow(
                    id=uuid4(),
                    tenant_id=tenant.value,
                    conversation_id=conversation,
                    correlation_id=uuid4(),
                    task="intent",
                    provider="fixture",
                    model="fixture",
                    prompt_id="fixture",
                    prompt_version=1,
                    schema_id="fixture",
                    status="success",
                    attempts=1,
                    latency_ms=1,
                    input_tokens=1,
                    output_tokens=1,
                    estimated_cost=Decimal("0"),
                    created_at=OLD,
                )
            )
        session.add(
            KnowledgeDocumentRow(
                id=document_id,
                tenant_id=tenant_a.value,
                title="Expired archive",
                locale="en",
                source_type="markdown",
                checksum="a" * 64,
                source_text="old",
                version=1,
                status="archived",
                metadata_json={},
                created_at=OLD,
                updated_at=OLD,
            )
        )
        await session.flush()
        session.add(
            KnowledgeChunkRow(
                id=chunk_id,
                tenant_id=tenant_a.value,
                document_id=document_id,
                document_version=1,
                ordinal=0,
                chunk_text="old",
                token_count=1,
                instruction_risk=False,
                metadata_json={},
                checksum="b" * 64,
            )
        )
        session.add(
            AuditEventRow(
                id=audit_id,
                tenant_id=tenant_a.value,
                actor_type="system",
                action="fixture",
                target_type="tenant",
                target_id=str(tenant_a),
                safe_diff={},
                correlation_id=uuid4(),
                occurred_at=OLD,
            )
        )

    application = PrivacyApplication(SQLAlchemyPrivacyStore(factory), Clock())
    owner = Principal("privacy-owner", tenant_a, Role.OWNER)
    preview = await application.preview_retention(owner)
    assert preview.dry_run and preview.counts["messages_deleted"] == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.tenant_id == tenant_a.value)
            )
            == 1
        )

    result = await application.execute_retention(
        owner, confirmed=True, idempotency_key="retention-2026-08-05"
    )
    replay = await application.execute_retention(
        owner, confirmed=True, idempotency_key="retention-2026-08-05"
    )
    assert replay.idempotent_replay and replay.action_id == result.action_id
    assert result.counts["knowledge_documents_deleted"] == 1
    assert result.counts["audit_events_preserved"] == 1
    async with factory() as session:
        for model in (MessageRow, TelegramUpdateRow, AIOperationRow):
            assert (
                await session.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_a.value)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant_b.value)
                )
                == 1
            )
        assert await session.get(KnowledgeDocumentRow, document_id) is None
        assert await session.get(AuditEventRow, audit_id) is not None
