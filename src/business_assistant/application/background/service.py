"""Reliable delivery orchestration with validated templates and bounded retries."""

import asyncio
from time import monotonic
from uuid import uuid4

from business_assistant.application.common.ports import Clock
from business_assistant.application.common.security import Permission, Principal
from business_assistant.application.observability import (
    Component,
    Operation,
    OperationalMetricsPort,
    Outcome,
    correlation_scope,
)

from .models import (
    DeliveryClaim,
    DeliveryOutcome,
    NotificationChannel,
    NotificationSubscription,
    RetryPolicy,
    WorkerHealth,
)
from .ports import BackgroundStorePort, NotificationGatewayPort

_SUPPORTED_EVENTS = frozenset(
    {
        "booking.confirmed",
        "booking.cancelled",
        "booking.rescheduled",
        "lead.qualified",
        "handoff.queued",
    }
)


class NotificationDeliveryError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__("Notification delivery failed")


class BackgroundApplication:
    def __init__(
        self,
        store: BackgroundStorePort,
        gateway: NotificationGatewayPort | None,
        clock: Clock,
        retry_policy: RetryPolicy,
        metrics: OperationalMetricsPort | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._clock = clock
        self._retry = retry_policy
        self._metrics = metrics

    async def create_subscription(
        self,
        principal: Principal,
        *,
        recipient_id: str,
        event_types: frozenset[str],
    ) -> NotificationSubscription:
        principal.require(Permission.NOTIFICATION_WRITE)
        if not event_types <= _SUPPORTED_EVENTS:
            raise ValueError("Notification event type is unsupported")
        return await self._store.save_subscription(
            NotificationSubscription(
                uuid4(),
                principal.tenant_id,
                NotificationChannel.TELEGRAM,
                recipient_id,
                event_types,
            )
        )

    async def list_subscriptions(
        self, principal: Principal
    ) -> tuple[NotificationSubscription, ...]:
        principal.require(Permission.NOTIFICATION_READ)
        return await self._store.list_subscriptions(principal.tenant_id)

    async def worker_health(self, principal: Principal) -> WorkerHealth:
        principal.require(Permission.WORKER_MONITOR_READ)
        health = await self._store.health(principal.tenant_id)
        if self._metrics is not None:
            self._metrics.set_backlog("outbox", health.pending_outbox)
            self._metrics.set_backlog("notifications", health.pending_notifications)
        return health

    async def dispatch_outbox(
        self, *, limit: int = 100, lease_seconds: int = 60
    ) -> tuple[int, int, int]:
        started = monotonic()
        result = await self._store.dispatch_outbox(
            now=self._clock.now(),
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=self._retry.max_attempts,
        )
        if self._metrics is not None:
            outcome = Outcome.DEAD_LETTER if result[2] else Outcome.SUCCESS
            self._metrics.observe(
                Component.OUTBOX, Operation.DISPATCH, outcome, monotonic() - started
            )
        return result

    async def deliver_notifications(
        self, *, limit: int = 100, lease_seconds: int = 60
    ) -> DeliveryOutcome:
        now = self._clock.now()
        started = monotonic()
        if self._gateway is None:
            raise RuntimeError("Notification gateway is not configured")
        claims = await self._store.claim_notifications(
            now=now, limit=limit, lease_seconds=lease_seconds
        )
        succeeded = retried = dead = 0
        for claim in claims:
            with correlation_scope(claim.correlation_id):
                try:
                    await self._gateway.send(claim, text=_render(claim))
                except asyncio.CancelledError:
                    raise
                except NotificationDeliveryError as exc:
                    if exc.retryable and claim.attempts < self._retry.max_attempts:
                        await self._store.retry_delivery(
                            claim,
                            at=self._retry.next_attempt_at(
                                claim_id=claim.id, attempts=claim.attempts, now=now
                            ),
                            error_code=exc.code,
                        )
                        retried += 1
                    else:
                        await self._store.dead_letter(claim, at=now, error_code=exc.code)
                        dead += 1
                except Exception:
                    if claim.attempts < self._retry.max_attempts:
                        await self._store.retry_delivery(
                            claim,
                            at=self._retry.next_attempt_at(
                                claim_id=claim.id, attempts=claim.attempts, now=now
                            ),
                            error_code="delivery.unexpected",
                        )
                        retried += 1
                    else:
                        await self._store.dead_letter(
                            claim, at=now, error_code="delivery.unexpected"
                        )
                        dead += 1
                else:
                    await self._store.mark_delivered(claim, at=now)
                    succeeded += 1
        outcome = DeliveryOutcome(len(claims), succeeded, retried, dead)
        if self._metrics is not None:
            result = Outcome.DEAD_LETTER if dead else Outcome.RETRY if retried else Outcome.SUCCESS
            self._metrics.observe(
                Component.NOTIFICATION,
                Operation.DELIVER,
                result,
                monotonic() - started,
            )
        return outcome


def _render(claim: DeliveryClaim) -> str:
    payload = claim.payload
    if claim.event_type == "lead.qualified":
        return (
            "A lead has qualified. "
            f"Lead ID: {_identifier(payload, 'lead_id')}. "
            f"Priority: {_choice(payload, 'priority', {'low', 'normal', 'high', 'urgent'})}."
        )
    if claim.event_type == "handoff.queued":
        return (
            "A staff handoff is queued. "
            f"Case ID: {_identifier(payload, 'handoff_id')}. "
            f"Priority: {_choice(payload, 'priority', {'low', 'normal', 'high', 'urgent'})}."
        )
    if claim.event_type in {
        "booking.confirmed",
        "booking.cancelled",
        "booking.rescheduled",
    }:
        action = claim.event_type.removeprefix("booking.")
        return (
            f"An appointment was {action}. "
            f"Reference: {_identifier(payload, 'public_reference')}. "
            f"Start: {_identifier(payload, 'start_at')}."
        )
    raise NotificationDeliveryError("delivery.unsupported_event", retryable=False)


def _identifier(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > 100:
        raise NotificationDeliveryError("delivery.invalid_payload", retryable=False)
    return value


def _choice(payload: dict[str, object], key: str, choices: set[str]) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) and value in choices else "normal"
