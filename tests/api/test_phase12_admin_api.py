from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient
from tests.helpers_phase3 import api_services, phase3_fixture

from business_assistant.application.administration import (
    CredentialIssue,
    CredentialView,
    MemberView,
    ProvisioningResult,
    TenantView,
)
from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import Locale
from business_assistant.domain.tenants import TenantStatus
from business_assistant.presentation.http import create_phase3_app


def test_admin_openapi_and_bootstrap_provisioning_are_typed_and_secret_safe() -> None:
    uow, base_principal, clock, key = phase3_fixture()
    principal = Principal(base_principal.subject, base_principal.tenant_id, Role.OWNER)
    administration = AsyncMock()
    now = datetime.now(UTC)
    member_id, credential_id = uuid4(), uuid4()
    tenant = TenantView(
        principal.tenant_id,
        "tenant-one",
        "Tenant One",
        "UTC",
        Locale.EN,
        frozenset({Locale.EN}),
        TenantStatus.SUSPENDED,
        1,
    )
    member = MemberView(
        member_id,
        principal.tenant_id,
        "owner@example.test",
        Role.OWNER,
        True,
        now,
        now,
    )
    credential = CredentialView(
        credential_id,
        principal.tenant_id,
        member_id,
        "owner-key",
        "atba_visible_prefix",
        Role.OWNER,
        None,
        None,
        None,
        now,
    )
    administration.provision.return_value = ProvisioningResult(
        tenant, member, CredentialIssue(credential, "one-time-secret"), True
    )
    services = replace(
        api_services(uow, principal, clock, key),
        administration=administration,
        bootstrap_token="bootstrap-test-token",
    )
    api = TestClient(create_phase3_app(services))

    schema = api.get("/openapi.json").json()
    assert "/api/v1/admin/tenant" in schema["paths"]
    assert "/api/v1/admin/credentials/{credential_id}/rotate" in schema["paths"]

    body = {
        "tenant_id": str(principal.tenant_id),
        "slug": "tenant-one",
        "name": "Tenant One",
        "timezone": "UTC",
        "owner_subject": "owner@example.test",
        "credential_name": "owner-key",
        "idempotency_key": "request-key-123",
        "enabled_capabilities": ["telegram"],
    }
    denied = api.post("/api/v1/admin/provisioning/tenants", json=body)
    assert denied.status_code == 401
    assert "bootstrap-test-token" not in denied.text

    response = api.post(
        "/api/v1/admin/provisioning/tenants",
        json=body,
        headers={"X-Admin-Bootstrap-Token": "bootstrap-test-token"},
    )
    assert response.status_code == 201
    assert response.json()["credential"]["secret"] == "one-time-secret"  # pragma: allowlist secret
    administration.provision.assert_awaited_once()
