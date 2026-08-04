"""Deterministic, identity-scoped qualification use cases."""

from business_assistant.application.common.errors import QualificationError
from business_assistant.application.common.ports import Clock
from business_assistant.application.common.security import Permission, Principal
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.leads import Lead, LeadPriority, LeadStatus
from business_assistant.domain.shared import (
    LeadId,
    QualificationSchemaId,
    QualificationSessionId,
)

from .engine import detect_handoff, next_missing_field, score_answers, validate_answer
from .models import (
    ConsentDecision,
    QualificationField,
    QualificationSchema,
    QualificationSession,
)
from .ports import QualificationStore


class QualificationApplication:
    def __init__(self, store: QualificationStore, clock: Clock, *, schema_code: str) -> None:
        self._store, self._clock, self._schema_code = store, clock, schema_code

    async def start(
        self, identity: TelegramIdentity
    ) -> tuple[QualificationSession, QualificationSchema]:
        now = self._clock.now()
        existing = await self._store.active_session(identity, now=now)
        schema = await self._store.published_schema(identity.tenant_id, self._schema_code)
        if schema is None:
            raise QualificationError("Qualification is not configured")
        return (existing or await self._store.start(identity, schema, now=now), schema)

    async def active(
        self, identity: TelegramIdentity
    ) -> tuple[QualificationSession, QualificationSchema] | None:
        session = await self._store.active_session(identity, now=self._clock.now())
        if session is None:
            return None
        schema = await self._store.schema(identity.tenant_id, session.schema_id)
        return (
            None
            if schema is None or schema.version != session.schema_version
            else (session, schema)
        )

    async def consent(
        self,
        identity: TelegramIdentity,
        session_id: QualificationSessionId,
        accepted: bool,
        update_key: str,
    ) -> tuple[QualificationSession, QualificationField | None]:
        session = await self._store.decide_consent(
            identity,
            session_id,
            ConsentDecision.ACCEPTED if accepted else ConsentDecision.DECLINED,
            now=self._clock.now(),
            update_key=update_key,
        )
        active = await self.active(identity)
        schema = active[1] if active is not None else None
        field = next_missing_field(schema, session.answers) if accepted and schema else None
        return session, field

    async def answer(
        self, identity: TelegramIdentity, raw: str, update_key: str
    ) -> tuple[QualificationSession, QualificationField | None]:
        active = await self.active(identity)
        if active is None:
            raise ValueError("No active qualification")
        session, schema_object = active
        field = next(
            (item for item in schema_object.fields if item.key == session.current_field_key), None
        )
        if field is None:
            raise ValueError("Qualification is not accepting an answer")
        answer = validate_answer(field, raw)
        session = await self._store.record_answer(
            identity, session.id, field.key, answer, now=self._clock.now(), update_key=update_key
        )
        return session, next_missing_field(schema_object, session.answers)

    async def edit(
        self, identity: TelegramIdentity, session_id: QualificationSessionId, field_key: str
    ) -> QualificationField:
        active = await self.active(identity)
        if active is None:
            raise ValueError("No active qualification")
        session, schema_object = active
        field = next((item for item in schema_object.fields if item.key == field_key), None)
        if field is None or session.id != session_id:
            raise ValueError("Qualification field is unavailable")
        await self._store.review(
            identity, session.id, now=self._clock.now(), edit_field_key=field.key
        )
        return field

    async def submit(
        self, identity: TelegramIdentity, session_id: QualificationSessionId, update_key: str
    ) -> QualificationSession:
        active = await self.active(identity)
        if active is None:
            raise ValueError("No active qualification")
        session, schema_object = active
        if (
            session.id != session_id
            or next_missing_field(schema_object, session.answers) is not None
        ):
            raise ValueError("Qualification is incomplete")
        score = score_answers(schema_object, session.answers)
        priority = {"A": LeadPriority.HIGH, "B": LeadPriority.NORMAL}.get(
            score.grade, LeadPriority.LOW
        )
        lead = Lead(
            LeadId.new(),
            identity.tenant_id,
            identity.customer_id,
            identity.conversation_id,
            schema_object.code,
            schema_object.version,
            "telegram",
            dict(session.answers),
            LeadStatus.QUALIFYING,
        )
        assert session.consent_at is not None
        lead.grant_consent(session.consent_at)
        lead.apply_deterministic_score(
            score.score,
            priority,
            {"grade": score.grade, "matched_rules": list(score.matched_rules)},
        )
        lead.qualify(
            snapshot={
                "schema_code": schema_object.code,
                "schema_version": schema_object.version,
                "answers": dict(session.answers),
            },
            qualified_at=self._clock.now(),
        )
        return await self._store.complete(
            identity,
            session.id,
            lead,
            score,
            detect_handoff(schema_object, session.answers),
            now=self._clock.now(),
            update_key=update_key,
        )

    async def cancel(self, identity: TelegramIdentity) -> bool:
        return await self._store.cancel(identity, now=self._clock.now())


class QualificationAdministration:
    def __init__(self, store: QualificationStore) -> None:
        self._store = store

    async def list_schemas(self, principal: Principal) -> tuple[QualificationSchema, ...]:
        principal.require(Permission.QUALIFICATION_SCHEMA_READ)
        return await self._store.list_schemas(principal.tenant_id)

    async def add_schema(
        self, principal: Principal, schema: QualificationSchema
    ) -> QualificationSchema:
        principal.require(Permission.QUALIFICATION_SCHEMA_WRITE)
        if schema.tenant_id != principal.tenant_id or schema.published:
            raise QualificationError(
                "New qualification schema versions must be tenant-owned drafts"
            )
        return await self._store.add_schema(schema)

    async def publish(
        self, principal: Principal, schema_id: QualificationSchemaId
    ) -> QualificationSchema:
        principal.require(Permission.QUALIFICATION_SCHEMA_WRITE)
        return await self._store.publish_schema(principal.tenant_id, schema_id)
