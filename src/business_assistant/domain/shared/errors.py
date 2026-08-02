"""Stable, provider-neutral domain errors."""

from dataclasses import dataclass


@dataclass(eq=False)
class DomainError(Exception):
    """Base error carrying a safe machine-readable code."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ValidationError(DomainError):
    def __init__(self, message: str, *, code: str = "domain.validation") -> None:
        super().__init__(code, message)


class InvalidStateTransition(DomainError):
    def __init__(self, aggregate: str, current: str, target: str) -> None:
        super().__init__(
            "domain.invalid_state_transition",
            f"{aggregate} cannot transition from {current} to {target}",
        )


class TenantMismatchError(DomainError):
    def __init__(self, relationship: str) -> None:
        super().__init__(
            "domain.tenant_mismatch",
            f"Cross-tenant relationship is forbidden: {relationship}",
        )
