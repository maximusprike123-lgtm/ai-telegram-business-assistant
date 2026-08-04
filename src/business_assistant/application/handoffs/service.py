"""Deterministic customer escalation and authorized staff lifecycle use cases."""

from datetime import timedelta

from business_assistant.application.common.errors import HandoffError
from business_assistant.application.common.ports import Clock
from business_assistant.application.common.security import Permission, Principal
from business_assistant.application.scheduling.engine import business_due_at
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.domain.shared import HandoffId, LeadId

from .models import HandoffView
from .ports import HandoffStore


class HandoffApplication:
    def __init__(self, store: HandoffStore, clock: Clock, *, response_minutes: int = 120) -> None:
        if not 1 <= response_minutes <= 10_080:
            raise ValueError("Handoff response time is invalid")
        self._store, self._clock = store, clock
        self._response_time = timedelta(minutes=response_minutes)

    async def request(
        self,
        identity: TelegramIdentity,
        *,
        reason_code: str,
        priority: str,
        summary: str,
        idempotency_key: str,
        context: dict[str, object] | None = None,
        lead_id: LeadId | None = None,
    ) -> HandoffView:
        now = self._clock.now()
        schedule = await self._store.schedule(identity.tenant_id)
        if schedule is None:
            raise ValueError("Handoff schedule is unavailable")
        due = business_due_at(schedule, now, self._response_time)
        try:
            return await self._store.create_or_get(
                identity,
                reason_code=reason_code,
                priority=priority,
                summary=summary,
                context={"timezone": schedule.timezone, **dict(context or {})},
                lead_id=lead_id,
                response_due_at=due,
                idempotency_key=idempotency_key,
                now=now,
            )
        except ValueError as exc:
            raise HandoffError() from exc

    async def active(self, identity: TelegramIdentity) -> HandoffView | None:
        return await self._store.active(identity)

    async def list_open(self, principal: Principal, *, limit: int = 50) -> tuple[HandoffView, ...]:
        principal.require(Permission.HANDOFF_READ)
        if not 1 <= limit <= 100:
            raise ValueError("Handoff list limit is invalid")
        return tuple(await self._store.list_open(principal.tenant_id, limit=limit))

    async def transition(
        self, principal: Principal, handoff_id: HandoffId, action: str
    ) -> HandoffView:
        principal.require(Permission.HANDOFF_WRITE)
        if action not in {"claim", "resolve", "reopen", "return_to_bot"}:
            raise ValueError("Handoff action is unsupported")
        try:
            return await self._store.transition(
                principal.tenant_id,
                handoff_id,
                action=action,
                actor_id=principal.subject,
                now=self._clock.now(),
            )
        except ValueError as exc:
            raise HandoffError() from exc
