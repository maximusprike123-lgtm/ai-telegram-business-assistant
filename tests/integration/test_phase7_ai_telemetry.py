from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.ai import (
    AICompletionStatus,
    AIOperationRecord,
    AITask,
)
from business_assistant.domain.shared import TenantId
from business_assistant.infrastructure.persistence import (
    SQLAlchemyAITelemetryStore,
    SQLAlchemyTelegramIdentityStore,
)
from business_assistant.infrastructure.persistence.seed import NORTHSTAR_TENANT_ID, seed_northstar
from business_assistant.infrastructure.persistence.sqlalchemy.models import AIOperationRow

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_ai_telemetry_is_tenant_scoped_metadata_only_and_rejects_cross_tenant_link(
    postgresql_url: str,
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    engine, factory = database
    await seed_northstar(postgresql_url, "test")
    now = datetime(2026, 8, 4, tzinfo=UTC)
    identity = await SQLAlchemyTelegramIdentityStore(factory).resolve(
        NORTHSTAR_TENANT_ID,
        external_user_id="7001",
        external_chat_id="7001",
        requested_locale="en",
        now=now,
    )
    operation = AIOperationRecord(
        uuid4(),
        NORTHSTAR_TENANT_ID,
        identity.conversation_id,
        uuid4(),
        AITask.INTENT,
        "fixture",
        "fixture-model",
        "intent-router",
        1,
        "intent-v1",
        AICompletionStatus.SUCCESS,
        1,
        42,
        12,
        4,
        Decimal("0.0001"),
        None,
        now,
    )
    store = SQLAlchemyAITelemetryStore(factory)
    await store.record(operation)
    async with factory() as session:
        row = await session.scalar(select(AIOperationRow))
    assert row is not None
    assert row.tenant_id == NORTHSTAR_TENANT_ID.value
    assert (row.task, row.status, row.latency_ms) == ("intent", "success", 42)
    assert row.estimated_cost == Decimal("0.0001000000")

    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync: {item["name"] for item in inspect(sync).get_columns("ai_operations")}
        )
    assert not columns & {"input_text", "output_text", "prompt_text", "provider_response"}

    with pytest.raises(IntegrityError):
        await store.record(
            AIOperationRecord(
                uuid4(),
                TenantId.new(),
                identity.conversation_id,
                uuid4(),
                AITask.INTENT,
                "fixture",
                "fixture-model",
                "intent-router",
                1,
                "intent-v1",
                AICompletionStatus.FALLBACK,
                1,
                5,
                0,
                0,
                Decimal(0),
                None,
                now,
            )
        )
