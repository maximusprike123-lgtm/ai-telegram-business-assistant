from uuid import uuid4

import pytest

from business_assistant.domain.shared import InvalidStateTransition, Locale, TenantId
from business_assistant.domain.tenants import Tenant, TenantStatus
from business_assistant.infrastructure.security import PBKDF2CredentialSecrets


def _tenant(status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        TenantId(uuid4()),
        "tenant-one",
        "Tenant One",
        "UTC",
        Locale.EN,
        frozenset({Locale.EN}),
        status,
    )


def test_tenant_lifecycle_is_explicit_idempotent_and_archive_is_terminal() -> None:
    tenant = _tenant()

    tenant.transition_to(TenantStatus.SUSPENDED)
    tenant.transition_to(TenantStatus.SUSPENDED)
    assert not tenant.can_process_new_work

    tenant.transition_to(TenantStatus.ACTIVE)
    assert tenant.can_process_new_work

    tenant.transition_to(TenantStatus.ARCHIVED)
    tenant.transition_to(TenantStatus.ARCHIVED)
    with pytest.raises(InvalidStateTransition):
        tenant.transition_to(TenantStatus.ACTIVE)


def test_credential_material_is_random_hashed_and_tamper_evident() -> None:
    secrets = PBKDF2CredentialSecrets()

    first = secrets.issue()
    second = secrets.issue()

    assert first.plaintext != second.plaintext
    assert first.plaintext not in first.secret_hash
    assert secrets.verify(first.plaintext, first.secret_hash)
    assert not secrets.verify(f"{first.plaintext}x", first.secret_hash)
    assert not secrets.verify(first.plaintext, "invalid")
