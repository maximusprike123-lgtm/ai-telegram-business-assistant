import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from business_assistant.application.administration import (
    AdministrationError,
    BusinessProfileView,
    Capability,
    ProvisionTenant,
    TenantAdministration,
)
from business_assistant.application.common.errors import AuthenticationError
from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import Locale, TenantId
from business_assistant.domain.tenants import TenantStatus
from business_assistant.infrastructure.persistence import (
    SQLAlchemyTenantAccessPolicy,
    SQLAlchemyTenantAdministrationStore,
)
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    AdministrativeCredentialRow,
    AuditEventRow,
)
from business_assistant.infrastructure.security import (
    DatabaseApiKeyAuthenticator,
    PBKDF2CredentialSecrets,
)


@pytest.mark.asyncio
async def test_provisioning_lifecycle_credentials_and_entitlements(database) -> None:
    _, factory = database
    tenant_id = TenantId(uuid4())
    secrets = PBKDF2CredentialSecrets()
    store = SQLAlchemyTenantAdministrationStore(factory)
    service = TenantAdministration(store, secrets)
    request = ProvisionTenant(
        tenant_id,
        "phase-twelve",
        "Phase Twelve",
        "UTC",
        Locale.EN,
        "owner@example.test",
        "initial-owner",
        "phase12-idempotency-key",
        frozenset({Capability.TELEGRAM, Capability.BOOKING}),
    )

    created = await service.provision(request)
    replay = await service.provision(request)
    assert created.created and created.credential.secret is not None
    assert not replay.created and replay.credential.secret is None
    assert created.tenant.status is TenantStatus.SUSPENDED

    authenticator = DatabaseApiKeyAuthenticator(factory, secrets)
    principal = await authenticator.authenticate(created.credential.secret)
    assert principal == Principal("owner@example.test", tenant_id, Role.OWNER)

    initial_profile = await service.business_profile(principal)
    updated_profile = await service.update_business_profile(
        principal,
        BusinessProfileView(
            "An English-only fictional business.",
            "+1 555 010 0300",
            "owner@example.test",
            "https://example.test",
            "1 Demo Street",
            "Demo City",
            "Parking at the entrance.",
            ("card",),
            "Demo warranty policy.",
            "Appointments require confirmation.",
            initial_profile.version,
        ),
        expected_version=initial_profile.version,
    )
    assert updated_profile.version == initial_profile.version + 1
    assert (await service.business_profile(principal)).public_email == "owner@example.test"

    access = SQLAlchemyTenantAccessPolicy(factory)
    with pytest.raises(AdministrationError, match="unavailable"):
        await access.require_active(tenant_id, Capability.BOOKING)
    active = await service.transition(principal, TenantStatus.ACTIVE)
    assert active.status is TenantStatus.ACTIVE
    await access.require_active(tenant_id, Capability.BOOKING)
    with pytest.raises(AdministrationError, match="disabled"):
        await access.require_active(tenant_id, Capability.KNOWLEDGE_ANSWERS)

    entitlements = await service.entitlements(principal)
    knowledge = next(
        item for item in entitlements if item.capability is Capability.KNOWLEDGE_ANSWERS
    )
    changed = await service.set_entitlement(
        principal,
        Capability.KNOWLEDGE_ANSWERS,
        enabled=True,
        expected_version=knowledge.version,
    )
    assert changed.enabled
    await access.require_active(tenant_id, Capability.KNOWLEDGE_ANSWERS)

    manager = await service.upsert_member(
        principal, subject="manager@example.test", role=Role.MANAGER
    )
    issued = await service.create_credential(
        principal,
        member_id=manager.id,
        name="manager-key",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    assert issued.secret is not None
    assert (await authenticator.authenticate(issued.secret)).role is Role.MANAGER
    async with factory() as session, session.begin():
        await session.execute(
            update(AdministrativeCredentialRow)
            .where(AdministrativeCredentialRow.id == issued.credential.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(AuthenticationError):
        await authenticator.authenticate(issued.secret)
    async with factory() as session, session.begin():
        await session.execute(
            update(AdministrativeCredentialRow)
            .where(AdministrativeCredentialRow.id == issued.credential.id)
            .values(expires_at=datetime.now(UTC) + timedelta(days=1))
        )

    rotated = await service.rotate_credential(principal, issued.credential.id, expires_at=None)
    with pytest.raises(AuthenticationError):
        await authenticator.authenticate(issued.secret)
    assert rotated.secret is not None
    assert (await authenticator.authenticate(rotated.secret)).subject == "manager@example.test"
    await service.revoke_credential(principal, rotated.credential.id)
    with pytest.raises(AuthenticationError):
        await authenticator.authenticate(rotated.secret)

    with pytest.raises(AdministrationError, match="owner"):
        await service.revoke_member(principal, created.owner.id)
    archived = await service.transition(principal, TenantStatus.ARCHIVED)
    assert archived.status is TenantStatus.ARCHIVED
    with pytest.raises(AdministrationError):
        await service.transition(principal, TenantStatus.ACTIVE)

    async with factory() as session:
        audits = (await session.scalars(select(AuditEventRow))).all()
    serialized = repr([item.safe_diff for item in audits])
    assert created.credential.secret not in serialized
    assert rotated.secret not in serialized


@pytest.mark.asyncio
async def test_provisioning_idempotency_key_cannot_cross_tenants(database) -> None:
    _, factory = database
    service = TenantAdministration(
        SQLAlchemyTenantAdministrationStore(factory), PBKDF2CredentialSecrets()
    )

    def request(tenant_id: TenantId) -> ProvisionTenant:
        return ProvisionTenant(
            tenant_id,
            f"tenant-{str(tenant_id)[:8]}",
            "Tenant",
            "UTC",
            Locale.EN,
            "owner",
            "owner-key",
            "shared-idempotency-key",
            frozenset(),
        )

    await service.provision(request(TenantId(uuid4())))
    with pytest.raises(AdministrationError, match="conflicts"):
        await service.provision(request(TenantId(uuid4())))


@pytest.mark.asyncio
async def test_concurrent_provisioning_has_one_authoritative_result(database) -> None:
    _, factory = database
    service = TenantAdministration(
        SQLAlchemyTenantAdministrationStore(factory), PBKDF2CredentialSecrets()
    )
    tenant_id = TenantId(uuid4())
    request = ProvisionTenant(
        tenant_id,
        f"concurrent-{str(tenant_id)[:8]}",
        "Concurrent Tenant",
        "UTC",
        Locale.EN,
        "owner@example.test",
        "owner-key",
        f"provision-{tenant_id}",
        frozenset(),
    )
    results = await asyncio.gather(service.provision(request), service.provision(request))
    assert sorted(result.created for result in results) == [False, True]
    assert sum(result.credential.secret is not None for result in results) == 1
