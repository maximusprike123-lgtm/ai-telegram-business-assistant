from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient
from tests.helpers_phase3 import api_services, phase3_fixture

from business_assistant.application.bookings import (
    AvailabilityContext,
    AvailableResource,
    BookingApplication,
    BookingPolicy,
)
from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import ResourceId
from business_assistant.presentation.http import create_phase3_app


def client(role: Role = Role.VIEWER) -> tuple[TestClient, str, Principal]:
    uow, principal, clock, key = phase3_fixture()
    principal = Principal(principal.subject, principal.tenant_id, role)
    app = create_phase3_app(api_services(uow, principal, clock, key))
    return TestClient(app), key, principal


def test_valid_authenticated_english_fallback_and_request_id() -> None:
    api, key, _ = client()
    response = api.get(
        "/api/v1/catalog/services?locale=es",
        headers={"X-Internal-API-Key": key, "X-Request-ID": "request-123"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"
    assert response.json()[0]["locale"] == "en"
    assert response.json()[0]["duration_display"] == "1 hour 30 minutes"


def test_missing_and_invalid_credentials_are_401_without_secret_echo() -> None:
    api, _, _ = client()
    missing = api.get("/api/v1/catalog/categories")
    invalid = api.get(
        "/api/v1/catalog/categories", headers={"X-Internal-API-Key": "do-not-leak-me"}
    )
    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.json()["code"] == "auth.authentication_required"
        assert "do-not-leak-me" not in response.text
        assert response.headers["WWW-Authenticate"] == "ApiKey"


def test_insufficient_role_and_cross_tenant_assertion_are_403() -> None:
    denied, key, _ = client(Role.KNOWLEDGE_EDITOR)
    response = denied.get("/api/v1/catalog/services", headers={"X-Internal-API-Key": key})
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"

    api, key, _ = client()
    mismatch = api.get(
        "/api/v1/catalog/services",
        headers={
            "X-Internal-API-Key": key,
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert mismatch.status_code == 403


def test_stable_validation_error_and_no_internal_exception_leakage() -> None:
    api, key, _ = client()
    invalid = api.get("/api/v1/catalog/services/not-a-uuid", headers={"X-Internal-API-Key": key})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request.invalid"
    assert invalid.json()["correlation_id"]

    def boom() -> None:
        raise RuntimeError("database-password-must-not-leak")

    api.app.add_api_route("/boom", boom)
    unsafe = TestClient(api.app, raise_server_exceptions=False).get("/boom")
    assert unsafe.status_code == 500
    assert unsafe.json()["code"] == "internal.error"
    assert "database-password" not in unsafe.text


def test_openapi_documents_versioned_endpoints_and_api_key_scheme() -> None:
    api, _, _ = client()
    schema = api.get("/openapi.json").json()
    assert schema["info"]["title"] == "AI Telegram Business Assistant Internal API"
    assert "InternalApiKey" in schema["components"]["securitySchemes"]
    for path in (
        "/api/v1/tenant/profile",
        "/api/v1/catalog/categories",
        "/api/v1/catalog/services",
        "/api/v1/catalog/services/{service_id}",
        "/api/v1/business-hours",
        "/api/v1/business-status",
        "/api/v1/next-opening",
    ):
        assert path in schema["paths"]


def test_phase5_availability_endpoint_is_authenticated_and_tenant_derived() -> None:
    uow, principal, clock, key = phase3_fixture()

    class AvailabilityStore:
        async def availability_context(self, tenant_id, service_id, *, now):
            service = await uow.services.get_active(tenant_id, service_id)
            assert service is not None
            return AvailabilityContext(
                tenant_id,
                service_id,
                "Exact service",
                service.duration,
                service.cleanup_buffer,
                service.active,
                service.bookable,
                BookingPolicy(
                    timedelta(minutes=30),
                    timedelta(days=30),
                    timedelta(hours=1),
                    timedelta(minutes=5),
                    timedelta(minutes=30),
                    timedelta(hours=24),
                    100,
                    32,
                    500,
                ),
                (AvailableResource(ResourceId.new(), uow.schedules.schedule, 1, True),),
            )

    base = api_services(uow, principal, clock, key)
    services = replace(
        base,
        bookings=BookingApplication(AvailabilityStore(), clock),  # type: ignore[arg-type]
    )
    api = TestClient(create_phase3_app(services))
    path = f"/api/v1/availability?service_id={uow.services.services[0].id}&local_date=2026-08-03"
    unauthorized = api.get(path)
    assert unauthorized.status_code == 401
    response = api.get(path, headers={"X-Internal-API-Key": key})
    assert response.status_code == 200
    assert response.json()
    assert response.json()[0]["timezone"] == "Europe/Moscow"
    assert "/api/v1/availability" in api.get("/openapi.json").json()["paths"]
