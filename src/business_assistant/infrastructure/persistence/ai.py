"""PostgreSQL adapter for metadata-only AI operation telemetry."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.ai import AIOperationRecord

from .sqlalchemy.models import AIOperationRow


class SQLAlchemyAITelemetryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, operation: AIOperationRecord) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(
                AIOperationRow(
                    id=operation.operation_id,
                    tenant_id=operation.tenant_id.value,
                    conversation_id=(
                        operation.conversation_id.value if operation.conversation_id else None
                    ),
                    correlation_id=operation.correlation_id,
                    task=operation.task.value,
                    provider=operation.provider,
                    model=operation.model,
                    prompt_id=operation.prompt_id,
                    prompt_version=operation.prompt_version,
                    schema_id=operation.schema_id,
                    status=operation.status.value,
                    attempts=operation.attempts,
                    latency_ms=operation.latency_ms,
                    input_tokens=operation.input_tokens,
                    output_tokens=operation.output_tokens,
                    estimated_cost=operation.estimated_cost,
                    failure_code=(
                        operation.failure_code.value if operation.failure_code is not None else None
                    ),
                    created_at=operation.occurred_at,
                )
            )
