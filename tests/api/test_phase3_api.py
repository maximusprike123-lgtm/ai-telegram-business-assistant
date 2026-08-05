from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from tests.helpers_phase3 import api_services, phase3_fixture

from business_assistant.application.bookings import (
    AvailabilityContext,
    AvailableResource,
    BookingApplication,
    BookingPolicy,
)
from business_assistant.application.common.security import Permission, Principal, Role
from business_assistant.application.knowledge import (
    KnowledgeAnswer,
    KnowledgeDocumentView,
    KnowledgeEvidence,
    KnowledgeSourceType,
    RetrievedKnowledgeChunk,
)
from business_assistant.application.privacy import CLASSIFICATIONS, PrivacyResult, RetentionPolicy
from business_assistant.domain.shared import Citation, Confidence, DocumentId, Locale, ResourceId
from business_assistant.infrastructure.security import StaticApiKeyAuthenticator
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


def test_phase8_knowledge_endpoints_are_authenticated_and_document_citations() -> None:
    uow, principal, clock, key = phase3_fixture()
    document_id, chunk_id = DocumentId.new(), uuid4()

    class KnowledgeFixture:
        async def ingest_markdown(self, actor, **kwargs):
            assert actor.tenant_id == principal.tenant_id
            assert kwargs["locale"] == "en"
            return document(None)

        async def ingest_faq(self, actor, **kwargs):
            assert kwargs["priority"] == 10
            return document(None, source_type=KnowledgeSourceType.FAQ)

        async def publish(self, actor, requested_id):
            assert requested_id == document_id
            return document(datetime(2026, 8, 4, tzinfo=UTC))

        async def archive(self, actor, requested_id):
            assert requested_id == document_id
            return KnowledgeDocumentView(
                document_id,
                "Warranty",
                Locale.EN,
                KnowledgeSourceType.MARKDOWN,
                "a" * 64,
                1,
                "archived",
                None,
                1,
            )

        async def answer(self, actor, **kwargs):
            chunk = RetrievedKnowledgeChunk(
                document_id,
                1,
                chunk_id,
                "Warranty",
                Locale.EN,
                KnowledgeSourceType.MARKDOWN,
                "Warranty requires inspection.",
                "Warranty",
                "b" * 64,
                0.9,
                1,
                1,
            )
            return KnowledgeAnswer(
                True,
                chunk.text,
                (
                    KnowledgeEvidence(
                        chunk, Citation(document_id, 1, str(chunk_id), Confidence(0.9), "b" * 64)
                    ),
                ),
            )

    def document(
        published_at, *, source_type=KnowledgeSourceType.MARKDOWN
    ) -> KnowledgeDocumentView:
        return KnowledgeDocumentView(
            document_id,
            "Warranty",
            Locale.EN,
            source_type,
            "a" * 64,
            1,
            "ready",
            published_at,
            1,
        )

    services = replace(api_services(uow, principal, clock, key), knowledge=KnowledgeFixture())
    api = TestClient(create_phase3_app(services))
    headers = {"X-Internal-API-Key": key}
    assert (
        api.post(
            "/api/v1/knowledge/markdown",
            headers=headers,
            json={"title": "Warranty", "markdown": "# Warranty\nInspection required."},
        ).status_code
        == 201
    )
    assert (
        api.post(
            "/api/v1/knowledge/faqs",
            headers=headers,
            json={"question": "Question?", "answer": "Answer.", "priority": 10},
        ).status_code
        == 201
    )
    published = api.post(f"/api/v1/knowledge/documents/{document_id}/publish", headers=headers)
    assert published.status_code == 200 and published.json()["published_at"]
    answer = api.post(
        "/api/v1/knowledge/test-answer",
        headers=headers,
        json={"query": "What is required?"},
    )
    assert answer.status_code == 200
    assert answer.json()["citations"][0]["chunk_id"] == str(chunk_id)
    assert (
        api.post("/api/v1/knowledge/test-answer", json={"query": "What is required?"}).status_code
        == 401
    )
    schema = api.get("/openapi.json").json()
    assert "/api/v1/knowledge/test-answer" in schema["paths"]


def test_phase9_privacy_endpoints_are_owner_controlled_tenant_derived_and_documented() -> None:
    uow, principal, clock, key = phase3_fixture()
    principal = Principal(principal.subject, principal.tenant_id, Role.OWNER)
    policy = RetentionPolicy(principal.tenant_id, 1, 30, 90, 365, 730, 365, 90)

    class PrivacyFixture:
        def classifications(self, actor):
            assert actor.tenant_id == principal.tenant_id
            return CLASSIFICATIONS

        async def get_policy(self, actor):
            actor.require(Permission.PRIVACY_READ)
            return policy

        async def update_policy(self, actor, requested, *, expected_version):
            assert actor.tenant_id == principal.tenant_id
            assert expected_version == 1
            return requested

        async def anonymize_customer(self, actor, customer_id, **kwargs):
            assert actor.tenant_id == principal.tenant_id
            assert kwargs["confirmed"] is True
            return PrivacyResult(
                "action-1", "customer_anonymization", False, 1, {"customers_anonymized": 1}
            )

        async def preview_retention(self, actor):
            return PrivacyResult(None, "retention_preview", True, 1, {"messages_deleted": 2})

        async def execute_retention(self, actor, **kwargs):
            assert kwargs["confirmed"] is True
            return PrivacyResult(
                "action-2", "retention_execution", False, 1, {"messages_deleted": 2}
            )

    services = replace(
        api_services(uow, principal, clock, key),
        privacy=PrivacyFixture(),  # type: ignore[arg-type]
    )
    api = TestClient(create_phase3_app(services))
    headers = {"X-Internal-API-Key": key}
    classifications = api.get("/api/v1/privacy/data-classifications", headers=headers)
    assert classifications.status_code == 200
    assert classifications.json()[0]["data_class"] == "operational_metadata"
    assert (
        api.get("/api/v1/privacy/retention-policy", headers=headers).json()["message_content_days"]
        == 90
    )
    update = api.put(
        "/api/v1/privacy/retention-policy",
        headers=headers,
        json={
            "expected_version": 1,
            "operational_metadata_days": 30,
            "message_content_days": 60,
            "customer_contact_days": 365,
            "workflow_records_days": 730,
            "knowledge_archive_days": 365,
            "ai_telemetry_days": 90,
        },
    )
    assert update.status_code == 200 and update.json()["version"] == 2
    anonymized = api.post(
        f"/api/v1/privacy/customers/{uuid4()}/anonymize",
        headers=headers,
        json={
            "confirmed": True,
            "idempotency_key": "customer-request-1",
            "reason_code": "customer_request",
        },
    )
    assert anonymized.status_code == 200
    assert anonymized.json()["counts"]["customers_anonymized"] == 1
    assert api.get("/api/v1/privacy/retention-preview", headers=headers).json()["dry_run"]
    executed = api.post(
        "/api/v1/privacy/retention-executions",
        headers=headers,
        json={"confirmed": True, "idempotency_key": "retention-1"},
    )
    assert executed.status_code == 200 and executed.json()["action_id"] == "action-2"
    schema = api.get("/openapi.json").json()
    for path in (
        "/api/v1/privacy/data-classifications",
        "/api/v1/privacy/retention-policy",
        "/api/v1/privacy/customers/{customer_id}/anonymize",
        "/api/v1/privacy/retention-preview",
        "/api/v1/privacy/retention-executions",
    ):
        assert path in schema["paths"]

    viewer = Principal(principal.subject, principal.tenant_id, Role.VIEWER)
    denied_services = replace(
        services,
        authenticator=StaticApiKeyAuthenticator(key, viewer),
    )
    denied = TestClient(create_phase3_app(denied_services)).get(
        "/api/v1/privacy/retention-policy", headers=headers
    )
    assert denied.status_code == 403
