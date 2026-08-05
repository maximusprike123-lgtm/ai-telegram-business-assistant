"""Prometheus-compatible adapter with a fixed low-cardinality label vocabulary."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from business_assistant.application.observability import (
    Component,
    Operation,
    OperationalMetricsPort,
    Outcome,
)

_QUEUES = frozenset({"default", "notifications", "maintenance", "knowledge", "outbox"})


class PrometheusMetrics(OperationalMetricsPort):
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)
        self.operations = Counter(
            "business_assistant_operations_total",
            "Bounded application operations",
            ("component", "operation", "outcome"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "business_assistant_operation_duration_seconds",
            "Bounded application operation latency",
            ("component", "operation", "outcome"),
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
            registry=self.registry,
        )
        self.backlog = Gauge(
            "business_assistant_backlog_items",
            "Durable pending work by bounded queue",
            ("queue",),
            registry=self.registry,
        )

    def observe(
        self,
        component: Component,
        operation: Operation,
        outcome: Outcome,
        duration_seconds: float,
    ) -> None:
        labels = (component.value, operation.value, outcome.value)
        self.operations.labels(*labels).inc()
        self.duration.labels(*labels).observe(max(0.0, duration_seconds))

    def set_backlog(self, queue: str, value: int) -> None:
        if queue not in _QUEUES:
            raise ValueError("Metric queue label is unsupported")
        self.backlog.labels(queue).set(max(0, value))

    def render(self) -> bytes:
        return generate_latest(self.registry)
