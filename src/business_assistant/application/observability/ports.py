"""Observability ports kept free of monitoring vendor SDKs."""

from typing import Protocol

from .models import Component, DiagnosticReport, Operation, Outcome


class OperationalMetricsPort(Protocol):
    def observe(
        self,
        component: Component,
        operation: Operation,
        outcome: Outcome,
        duration_seconds: float,
    ) -> None: ...

    def set_backlog(self, queue: str, value: int) -> None: ...

    def render(self) -> bytes: ...


class HealthCheckPort(Protocol):
    async def check(self) -> DiagnosticReport: ...
