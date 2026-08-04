"""Persistence boundary for the deterministic qualification workflow."""

from datetime import datetime
from typing import Protocol

from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.leads import Lead
from business_assistant.domain.shared import (
    LeadId,
    QualificationSchemaId,
    QualificationSessionId,
    TenantId,
)

from .models import (
    Answer,
    ConsentDecision,
    QualificationSchema,
    QualificationSession,
    ScoreResult,
    TriggerResult,
)


class QualificationStore(Protocol):
    async def published_schema(
        self, tenant_id: TenantId, code: str
    ) -> QualificationSchema | None: ...
    async def schema(
        self, tenant_id: TenantId, schema_id: QualificationSchemaId
    ) -> QualificationSchema | None: ...
    async def active_session(
        self, identity: TelegramIdentity, *, now: datetime
    ) -> QualificationSession | None: ...
    async def start(
        self, identity: TelegramIdentity, schema: QualificationSchema, *, now: datetime
    ) -> QualificationSession: ...
    async def decide_consent(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        decision: ConsentDecision,
        *,
        now: datetime,
        update_key: str,
    ) -> QualificationSession: ...
    async def record_answer(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        field_key: str,
        answer: Answer,
        *,
        now: datetime,
        update_key: str,
    ) -> QualificationSession: ...
    async def review(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        *,
        now: datetime,
        edit_field_key: str | None = None,
    ) -> QualificationSession: ...
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
    ) -> QualificationSession: ...
    async def cancel(self, identity: TelegramIdentity, *, now: datetime) -> bool: ...
    async def get_lead(self, tenant_id: TenantId, lead_id: LeadId) -> Lead | None: ...
    async def list_schemas(self, tenant_id: TenantId) -> tuple[QualificationSchema, ...]: ...
    async def add_schema(self, schema: QualificationSchema) -> QualificationSchema: ...
    async def publish_schema(
        self, tenant_id: TenantId, schema_id: QualificationSchemaId
    ) -> QualificationSchema: ...
