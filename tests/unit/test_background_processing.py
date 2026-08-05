from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from business_assistant.application.background import (
    BackgroundApplication,
    DeliveryClaim,
    NotificationChannel,
    NotificationDeliveryError,
    NotificationSubscription,
    RetryPolicy,
    WorkerHealth,
)
from business_assistant.application.common.errors import AuthorizationError
from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import TenantId


class Clock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class Store:
    def __init__(self, claims: tuple[DeliveryClaim, ...] = ()) -> None:
        self.claims = claims
        self.subscriptions: list[NotificationSubscription] = []
        self.completed: list[str] = []

    async def save_subscription(self, item: NotificationSubscription) -> NotificationSubscription:
        self.subscriptions.append(item)
        return item

    async def list_subscriptions(self, tenant_id: TenantId) -> tuple[NotificationSubscription, ...]:
        return tuple(item for item in self.subscriptions if item.tenant_id == tenant_id)

    async def dispatch_outbox(
        self, *, now: datetime, limit: int, lease_seconds: int, max_attempts: int
    ) -> tuple[int, int, int]:
        return limit, lease_seconds, max_attempts

    async def claim_notifications(
        self, *, now: datetime, limit: int, lease_seconds: int
    ) -> tuple[DeliveryClaim, ...]:
        return self.claims[:limit]

    async def mark_delivered(self, claim: DeliveryClaim, *, at: datetime) -> None:
        self.completed.append("sent")

    async def retry_delivery(self, claim: DeliveryClaim, *, at: datetime, error_code: str) -> None:
        assert at > NOW
        self.completed.append(f"retry:{error_code}")

    async def dead_letter(self, claim: DeliveryClaim, *, at: datetime, error_code: str) -> None:
        self.completed.append(f"dead:{error_code}")

    async def health(self, tenant_id: TenantId) -> WorkerHealth:
        return WorkerHealth(1, 2, 3, 4, NOW, NOW)


class Gateway:
    def __init__(self, error: NotificationDeliveryError | None = None) -> None:
        self.error = error
        self.messages: list[str] = []

    async def send(self, claim: DeliveryClaim, *, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(text)


NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)
TENANT = TenantId.new()


def claim(*, event_type: str = "lead.qualified", attempts: int = 1) -> DeliveryClaim:
    payload: dict[str, object] = {
        "lead_id": str(uuid4()),
        "handoff_id": str(uuid4()),
        "priority": "high",
    }
    return DeliveryClaim(
        UUID(int=1),
        TENANT,
        event_type,
        NotificationChannel.TELEGRAM,
        "12345",
        payload,
        attempts,
    )


@pytest.mark.asyncio
async def test_subscription_is_authorized_validated_and_tenant_scoped() -> None:
    store = Store()
    app = BackgroundApplication(store, Gateway(), Clock(NOW), RetryPolicy())
    owner = Principal("owner", TENANT, Role.OWNER)
    subscription = await app.create_subscription(
        owner, recipient_id="12345", event_types=frozenset({"lead.qualified"})
    )
    assert subscription.tenant_id == TENANT
    assert await app.list_subscriptions(owner) == (subscription,)
    assert (await app.worker_health(owner)).dead_letters == 4

    with pytest.raises(ValueError, match="unsupported"):
        await app.create_subscription(
            owner, recipient_id="12345", event_types=frozenset({"unknown.event"})
        )
    with pytest.raises(AuthorizationError):
        await app.list_subscriptions(Principal("viewer", TENANT, Role.VIEWER))


@pytest.mark.asyncio
async def test_validated_template_is_delivered_without_arbitrary_payload_text() -> None:
    item = claim()
    item.payload["untrusted"] = "<script>customer text</script>"
    store = Store((item,))
    gateway = Gateway()
    result = await BackgroundApplication(
        store, gateway, Clock(NOW), RetryPolicy()
    ).deliver_notifications()
    assert result.succeeded == 1
    assert store.completed == ["sent"]
    assert "customer text" not in gateway.messages[0]
    assert "Priority: high" in gateway.messages[0]


@pytest.mark.asyncio
async def test_transient_failure_retries_and_permanent_failure_dead_letters() -> None:
    transient_store = Store((claim(),))
    transient = BackgroundApplication(
        transient_store,
        Gateway(NotificationDeliveryError("telegram.network", retryable=True)),
        Clock(NOW),
        RetryPolicy(),
    )
    assert (await transient.deliver_notifications()).retried == 1
    assert transient_store.completed == ["retry:telegram.network"]

    permanent_store = Store((claim(),))
    permanent = BackgroundApplication(
        permanent_store,
        Gateway(NotificationDeliveryError("telegram.forbidden", retryable=False)),
        Clock(NOW),
        RetryPolicy(),
    )
    assert (await permanent.deliver_notifications()).dead_lettered == 1
    assert permanent_store.completed == ["dead:telegram.forbidden"]


@pytest.mark.asyncio
async def test_invalid_event_payload_dead_letters_deterministically() -> None:
    invalid = claim(event_type="handoff.queued")
    invalid.payload.pop("handoff_id")
    store = Store((invalid,))
    result = await BackgroundApplication(
        store, Gateway(), Clock(NOW), RetryPolicy()
    ).deliver_notifications()
    assert result.dead_lettered == 1
    assert store.completed == ["dead:delivery.invalid_payload"]


def test_retry_policy_uses_bounded_deterministic_backoff() -> None:
    policy = RetryPolicy(6, 5, 20)
    first = policy.next_attempt_at(claim_id=UUID(int=1), attempts=1, now=NOW)
    repeated = policy.next_attempt_at(claim_id=UUID(int=1), attempts=1, now=NOW)
    final = policy.next_attempt_at(claim_id=UUID(int=1), attempts=10, now=NOW)
    assert first == repeated
    assert 5 <= (first - NOW).total_seconds() <= 20
    assert (final - NOW).total_seconds() <= 20


def test_celery_routes_and_schedules_are_explicit() -> None:
    from tests.unit.test_configuration import valid_environment

    from business_assistant.bootstrap.worker import (
        DELIVERY_TASK,
        HOLD_TASK,
        OUTBOX_TASK,
        REINDEX_TASK,
        RETENTION_TASK,
        create_worker_app,
    )
    from business_assistant.config import load_settings

    app = create_worker_app(load_settings(valid_environment()))
    assert set(app.conf.beat_schedule) == {
        "dispatch-outbox",
        "deliver-notifications",
        "expire-holds",
        "execute-retention",
        "reindex-knowledge",
    }
    assert app.conf.task_routes[OUTBOX_TASK]["queue"] == "default"
    assert app.conf.task_routes[DELIVERY_TASK]["queue"] == "notifications"
    assert app.conf.task_routes[HOLD_TASK]["queue"] == "maintenance"
    assert app.conf.task_routes[RETENTION_TASK]["queue"] == "maintenance"
    assert app.conf.task_routes[REINDEX_TASK]["queue"] == "knowledge"
