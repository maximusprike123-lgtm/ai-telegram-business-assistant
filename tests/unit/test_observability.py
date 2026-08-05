import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO

from fastapi.testclient import TestClient
from tests.helpers_phase3 import api_services, phase3_fixture

from business_assistant.application.common.security import Principal, Role
from business_assistant.application.observability import (
    Component,
    DependencyCheck,
    DependencyStatus,
    DiagnosticReport,
    Operation,
    Outcome,
    correlation_scope,
    current_correlation_id,
    parse_or_create,
)
from business_assistant.infrastructure.observability import (
    PrometheusMetrics,
)
from business_assistant.infrastructure.observability.logging import SafeJsonFormatter
from business_assistant.presentation.http import OperationalApiServices, create_phase3_app


class FakeHealth:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready

    async def check(self) -> DiagnosticReport:
        return DiagnosticReport(
            self.ready,
            datetime(2026, 8, 5, tzinfo=UTC),
            (
                DependencyCheck(
                    "postgresql",
                    DependencyStatus.HEALTHY if self.ready else DependencyStatus.UNAVAILABLE,
                    True,
                    4,
                    None if self.ready else "dependency.database_unavailable",
                ),
                DependencyCheck("redis", DependencyStatus.DISABLED, False, 0),
            ),
        )


def _logger(stream: StringIO) -> logging.Logger:
    logger = logging.Logger("safe-test")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter())
    logger.addHandler(handler)
    return logger


def test_correlation_context_accepts_safe_ids_and_replaces_unsafe_values() -> None:
    assert parse_or_create("request-123") == "request-123"
    generated = parse_or_create("unsafe value\nsecret")
    assert generated != "unsafe value\nsecret"
    with correlation_scope("request-123"):
        assert current_correlation_id() == "request-123"
    assert current_correlation_id() != "request-123"


def test_safe_logger_drops_arbitrary_messages_and_context() -> None:
    stream = StringIO()
    logger = _logger(stream)
    logger.error(
        "Customer said %s",
        "private body",
        extra={"safe_context": {"tenant_id": "tenant", "prompt": "do not log"}},
    )
    payload = json.loads(stream.getvalue())
    assert payload == {
        "level": "ERROR",
        "event": "logging.unsafe_event",
        "tenant_id": "tenant",
    }
    assert "private body" not in stream.getvalue()


def test_prometheus_metrics_use_only_bounded_labels() -> None:
    metrics = PrometheusMetrics()
    metrics.observe(Component.AI, Operation.EXECUTE, Outcome.SUCCESS, 0.25)
    metrics.set_backlog("outbox", 3)
    rendered = metrics.render().decode()
    assert 'component="ai",operation="execute",outcome="success"' in rendered
    assert 'queue="outbox"' in rendered
    assert "tenant_id" not in rendered
    assert "correlation_id" not in rendered


def test_operational_endpoints_are_safe_authenticated_and_feature_gated() -> None:
    uow, principal, clock, key = phase3_fixture()
    stream = StringIO()
    metrics = PrometheusMetrics()
    operations = OperationalApiServices(metrics, FakeHealth(), _logger(stream), True, "metrics-key")
    services = replace(api_services(uow, principal, clock, key), operations=operations)
    api = TestClient(create_phase3_app(services))

    assert api.get("/health/live").json() == {"status": "alive"}
    assert api.get("/health/ready").json() == {"status": "ready"}
    assert api.get("/metrics").status_code == 401
    metrics_response = api.get("/metrics", headers={"Authorization": "Bearer metrics-key"})
    assert metrics_response.status_code == 200
    assert "business_assistant_operations_total" in metrics_response.text

    denied = api.get("/api/v1/operations/diagnostics", headers={"X-Internal-API-Key": key})
    assert denied.status_code == 403
    manager = Principal(principal.subject, principal.tenant_id, Role.MANAGER)
    manager_services = replace(
        services,
        authenticator=type(services.authenticator)(key, manager),
    )
    allowed = TestClient(create_phase3_app(manager_services)).get(
        "/api/v1/operations/diagnostics", headers={"X-Internal-API-Key": key}
    )
    assert allowed.status_code == 200
    assert allowed.json()["dependencies"][0]["name"] == "postgresql"
    assert key not in stream.getvalue()


def test_readiness_fails_without_exposing_exception_details() -> None:
    uow, principal, clock, key = phase3_fixture()
    operations = OperationalApiServices(
        PrometheusMetrics(), FakeHealth(ready=False), _logger(StringIO()), False, None
    )
    api = TestClient(
        create_phase3_app(replace(api_services(uow, principal, clock, key), operations=operations))
    )
    response = api.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert api.get("/metrics").status_code == 404
