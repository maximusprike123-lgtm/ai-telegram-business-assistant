"""Thin authenticated Phase 3 FastAPI presentation adapter."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from business_assistant.application.bookings import AvailableSlot, BookingApplication
from business_assistant.application.catalog import (
    GetService,
    ListServiceCategories,
    ListServices,
    ServiceCategoryDTO,
    ServiceDTO,
)
from business_assistant.application.common.errors import ApplicationError
from business_assistant.application.common.security import Principal
from business_assistant.application.handoffs import HandoffApplication, HandoffView
from business_assistant.application.knowledge import (
    KnowledgeAnswer,
    KnowledgeApplication,
    KnowledgeDocumentView,
)
from business_assistant.application.leads import (
    FieldValidation,
    GradeBand,
    HandoffTrigger,
    MatchOperator,
    QualificationAdministration,
    QualificationField,
    QualificationFieldType,
    QualificationSchema,
    ScoreRule,
    Sensitivity,
)
from business_assistant.application.privacy import (
    PrivacyApplication,
    PrivacyResult,
    RetentionPolicy,
)
from business_assistant.application.scheduling import (
    BusinessDayDTO,
    BusinessStatusDTO,
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
    NextOpeningDTO,
)
from business_assistant.application.tenants import GetTenantPublicProfile, TenantPublicProfileDTO
from business_assistant.domain.shared import (
    CategoryId,
    CustomerId,
    DocumentId,
    HandoffId,
    QualificationSchemaId,
    ServiceId,
)
from business_assistant.infrastructure.security import StaticApiKeyAuthenticator

from .schemas import (
    AvailabilitySlotResponse,
    BusinessDayResponse,
    BusinessStatusResponse,
    CategoryResponse,
    CustomerAnonymizationRequest,
    DataClassificationResponse,
    ErrorResponse,
    FAQKnowledgeCreate,
    HandoffActionRequest,
    HandoffResponse,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
    KnowledgeCitationResponse,
    KnowledgeDocumentResponse,
    MarkdownKnowledgeCreate,
    NextOpeningResponse,
    PrivacyExecutionRequest,
    PrivacyResultResponse,
    QualificationSchemaCreate,
    QualificationSchemaResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdate,
    ServiceResponse,
    TenantProfileResponse,
)


@dataclass(frozen=True, slots=True)
class Phase3ApiServices:
    profile: GetTenantPublicProfile
    categories: ListServiceCategories
    services: ListServices
    service: GetService
    hours: GetBusinessHours
    status: GetBusinessStatus
    next_opening: GetNextOpening
    authenticator: StaticApiKeyAuthenticator
    bookings: BookingApplication | None = None
    qualification_admin: QualificationAdministration | None = None
    handoffs: HandoffApplication | None = None
    knowledge: KnowledgeApplication | None = None
    privacy: PrivacyApplication | None = None


def _schema_response(schema: QualificationSchema) -> QualificationSchemaResponse:
    payload = asdict(schema)
    payload["id"] = str(schema.id)
    payload["session_ttl_minutes"] = int(schema.session_ttl.total_seconds() // 60)
    payload.pop("tenant_id")
    payload.pop("session_ttl")
    return QualificationSchemaResponse.model_validate(payload)


def _handoff_response(handoff: HandoffView) -> HandoffResponse:
    return HandoffResponse(
        id=str(handoff.id),
        conversation_id=str(handoff.conversation_id),
        lead_id=str(handoff.lead_id) if handoff.lead_id else None,
        reason_code=handoff.reason_code,
        priority=handoff.priority,
        status=handoff.status,
        summary=handoff.summary,
        context=handoff.context,
        response_due_at=handoff.response_due_at,
        assignee_id=handoff.assignee_id,
    )


def _knowledge_document_response(document: KnowledgeDocumentView) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=str(document.id),
        title=document.title,
        locale=document.locale.value,
        source_type=document.source_type.value,
        checksum=document.checksum,
        version=document.version,
        status=document.status,
        published_at=document.published_at,
        chunk_count=document.chunk_count,
    )


def _knowledge_answer_response(answer: KnowledgeAnswer) -> KnowledgeAnswerResponse:
    return KnowledgeAnswerResponse(
        answered=answer.answered,
        text=answer.text,
        citations=tuple(
            KnowledgeCitationResponse(
                document_id=str(item.citation.document_id),
                document_version=item.citation.document_version,
                chunk_id=item.citation.chunk_id,
                title=item.chunk.title,
                section=item.chunk.section,
                score=item.citation.score.value,
                content_checksum=item.citation.content_checksum,
            )
            for item in answer.evidence
        ),
        fallback_reason=answer.fallback_reason,
    )


def _retention_policy_response(policy: RetentionPolicy) -> RetentionPolicyResponse:
    return RetentionPolicyResponse(
        version=policy.version,
        operational_metadata_days=policy.operational_metadata_days,
        message_content_days=policy.message_content_days,
        customer_contact_days=policy.customer_contact_days,
        workflow_records_days=policy.workflow_records_days,
        knowledge_archive_days=policy.knowledge_archive_days,
        ai_telemetry_days=policy.ai_telemetry_days,
    )


def _privacy_result_response(result: PrivacyResult) -> PrivacyResultResponse:
    return PrivacyResultResponse(
        action_id=result.action_id,
        action=result.action,
        dry_run=result.dry_run,
        policy_version=result.policy_version,
        counts=dict(result.counts),
        idempotent_replay=result.idempotent_replay,
    )


def _qualification_schema(
    principal: Principal, request: QualificationSchemaCreate
) -> QualificationSchema:
    return QualificationSchema(
        QualificationSchemaId.new(),
        principal.tenant_id,
        request.code,
        request.version,
        request.title,
        request.consent_version,
        request.consent_purpose,
        tuple(
            QualificationField(
                item.key,
                item.label,
                item.prompt,
                QualificationFieldType(item.field_type),
                FieldValidation(
                    item.validation.min_length,
                    item.validation.max_length,
                    item.validation.minimum,
                    item.validation.maximum,
                    item.validation.options,
                    item.validation.pattern,
                ),
                item.required,
                item.order,
                Sensitivity(item.sensitivity),
                tuple(
                    ScoreRule(
                        rule.code,
                        MatchOperator(rule.operator),
                        rule.expected,
                        rule.points,
                    )
                    for rule in item.score_rules
                ),
                tuple(
                    HandoffTrigger(
                        rule.code,
                        MatchOperator(rule.operator),
                        rule.expected,
                        rule.reason_code,
                        rule.priority,
                    )
                    for rule in item.handoff_triggers
                ),
            )
            for item in request.fields
        ),
        tuple(GradeBand(item.minimum_score, item.grade) for item in request.grade_bands),
        timedelta(minutes=request.session_ttl_minutes),
        request.handoff_response_minutes,
        False,
        request.active,
    )


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def create_phase3_app(services: Phase3ApiServices) -> FastAPI:
    app = FastAPI(
        title="AI Telegram Business Assistant Internal API",
        version="1.0.0",
        description="Authenticated deterministic Phase 3 tenant, catalog, and hours queries.",
        openapi_tags=[
            {"name": "Tenant", "description": "Customer-safe tenant profile"},
            {"name": "Catalog", "description": "Localized active service catalog"},
            {"name": "Schedule", "description": "Tenant-local business hours"},
            {"name": "Booking", "description": "Resource-aware appointment availability"},
            {"name": "Qualification", "description": "Versioned lead qualification schemas"},
            {"name": "Handoff", "description": "Authorized human handoff operations"},
            {"name": "Knowledge", "description": "Tenant-scoped approved knowledge"},
            {"name": "Privacy", "description": "Tenant-scoped privacy and retention controls"},
        ],
    )
    key_header = APIKeyHeader(
        name="X-Internal-API-Key",
        scheme_name="InternalApiKey",
        description="Tenant-bound internal portfolio API key",
        auto_error=False,
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied = request.headers.get("X-Request-ID", "")
        correlation_id = (
            supplied if supplied.isascii() and 1 <= len(supplied) <= 128 else str(uuid4())
        )
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id
        return response

    async def authenticated_principal(
        request: Request,
        api_key: Annotated[str | None, Security(key_header)],
        asserted_tenant: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    ) -> Principal:
        principal = services.authenticator.authenticate(api_key)
        if asserted_tenant is not None and asserted_tenant != str(principal.tenant_id):
            from business_assistant.application.common.errors import AuthorizationError

            raise AuthorizationError()
        return principal

    PrincipalDependency = Annotated[Principal, Depends(authenticated_principal)]

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        status = (
            403
            if exc.code == "auth.forbidden"
            else 401
            if exc.code.startswith("auth.")
            else 409
            if exc.code
            in {
                "booking.conflict",
                "booking.expired",
                "privacy.policy_conflict",
                "privacy.idempotency_conflict",
            }
            else 404
            if exc.code.endswith("not_found")
            else 422
        )
        return JSONResponse(
            status_code=status,
            content={
                "code": exc.code,
                "message": exc.safe_message,
                "correlation_id": _correlation_id(request),
            },
            headers={"WWW-Authenticate": "ApiKey"} if status == 401 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": str(error["msg"])}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "request.invalid",
                "message": "Request validation failed",
                "correlation_id": _correlation_id(request),
                "details": details,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        _ = exc
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal.error",
                "message": "The request could not be completed",
                "correlation_id": _correlation_id(request),
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        _ = exc
        return JSONResponse(
            status_code=422,
            content={
                "code": "request.invalid",
                "message": "Request validation failed",
                "correlation_id": _correlation_id(request),
            },
        )

    error_responses: dict[int | str, dict[str, Any]] = {
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }

    @app.get(
        "/api/v1/tenant/profile",
        response_model=TenantProfileResponse,
        tags=["Tenant"],
        summary="Get the tenant public profile",
        description="Returns customer-safe business facts for the authenticated tenant only.",
        responses=error_responses,
    )
    async def get_profile(
        principal: PrincipalDependency, locale: str | None = None
    ) -> TenantPublicProfileDTO:
        return await services.profile.execute(principal, locale)

    @app.get(
        "/api/v1/catalog/categories",
        response_model=list[CategoryResponse],
        tags=["Catalog"],
        summary="List active service categories",
        description="Returns only active localized categories for the credential-bound tenant.",
        responses=error_responses,
    )
    async def list_categories(
        principal: PrincipalDependency, locale: str | None = None
    ) -> tuple[ServiceCategoryDTO, ...]:
        return await services.categories.execute(principal, locale)

    @app.get(
        "/api/v1/catalog/services",
        response_model=list[ServiceResponse],
        tags=["Catalog"],
        summary="List active services",
        description=(
            "Returns active localized services, optionally restricted to an active category."
        ),
        responses=error_responses,
    )
    async def list_services(
        principal: PrincipalDependency,
        locale: str | None = None,
        category_id: UUID | None = None,
    ) -> tuple[ServiceDTO, ...]:
        typed_category = CategoryId(category_id) if category_id is not None else None
        return await services.services.execute(principal, locale, typed_category)

    @app.get(
        "/api/v1/catalog/services/{service_id}",
        response_model=ServiceResponse,
        tags=["Catalog"],
        summary="Get an active service",
        description="Returns one customer-visible service without exposing persistence records.",
        responses=error_responses,
    )
    async def get_service(
        service_id: UUID, principal: PrincipalDependency, locale: str | None = None
    ) -> ServiceDTO:
        return await services.service.execute(principal, ServiceId(service_id), locale)

    @app.get(
        "/api/v1/business-hours",
        response_model=list[BusinessDayResponse],
        tags=["Schedule"],
        summary="Get business hours",
        description="Evaluates recurring hours and replacing date overrides in tenant-local time.",
        responses=error_responses,
    )
    async def get_hours(
        principal: PrincipalDependency,
        start_date: date,
        days: Annotated[int, Query(ge=1, le=31)] = 7,
        locale: str | None = None,
    ) -> tuple[BusinessDayDTO, ...]:
        return await services.hours.execute(principal, start_date, days=days, locale=locale)

    @app.get(
        "/api/v1/business-status",
        response_model=BusinessStatusResponse,
        tags=["Schedule"],
        summary="Get current open or closed status",
        description="Evaluates an aware instant, or the injected clock, in the tenant timezone.",
        responses=error_responses,
    )
    async def get_status(
        principal: PrincipalDependency, at: datetime | None = None
    ) -> BusinessStatusDTO:
        return await services.status.execute(principal, at)

    @app.get(
        "/api/v1/next-opening",
        response_model=NextOpeningResponse,
        tags=["Schedule"],
        summary="Get the next opening",
        description="Returns open-now or searches at most 370 tenant-local calendar days.",
        responses=error_responses,
    )
    async def get_next_opening(
        principal: PrincipalDependency, at: datetime | None = None
    ) -> NextOpeningDTO:
        return await services.next_opening.execute(principal, at)

    booking_application = services.bookings
    if booking_application is not None:

        @app.get(
            "/api/v1/availability",
            response_model=list[AvailabilitySlotResponse],
            tags=["Booking"],
            summary="List available appointment times",
            description=(
                "Returns deterministic resource-aware slots in tenant-local time. "
                "Displaying a slot does not reserve it."
            ),
            responses=error_responses,
        )
        async def get_availability(
            principal: PrincipalDependency,
            service_id: UUID,
            local_date: date,
        ) -> tuple[AvailableSlot, ...]:
            return await booking_application.availability(
                principal, ServiceId(service_id), local_date
            )

    qualification_admin = services.qualification_admin
    if qualification_admin is not None:

        @app.get(
            "/api/v1/qualification-schemas",
            response_model=list[QualificationSchemaResponse],
            tags=["Qualification"],
            summary="List qualification schema versions",
            responses=error_responses,
        )
        async def list_qualification_schemas(
            principal: PrincipalDependency,
        ) -> list[QualificationSchemaResponse]:
            schemas = await qualification_admin.list_schemas(principal)
            return [_schema_response(schema) for schema in schemas]

        @app.post(
            "/api/v1/qualification-schemas",
            response_model=QualificationSchemaResponse,
            status_code=201,
            tags=["Qualification"],
            summary="Create an unpublished qualification schema version",
            responses=error_responses,
        )
        async def create_qualification_schema(
            request: QualificationSchemaCreate,
            principal: PrincipalDependency,
        ) -> QualificationSchemaResponse:
            schema = _qualification_schema(principal, request)
            return _schema_response(await qualification_admin.add_schema(principal, schema))

        @app.post(
            "/api/v1/qualification-schemas/{schema_id}/publish",
            response_model=QualificationSchemaResponse,
            tags=["Qualification"],
            summary="Publish one qualification schema version",
            responses=error_responses,
        )
        async def publish_qualification_schema(
            schema_id: UUID,
            principal: PrincipalDependency,
        ) -> QualificationSchemaResponse:
            schema = await qualification_admin.publish(principal, QualificationSchemaId(schema_id))
            return _schema_response(schema)

    handoff_application = services.handoffs
    if handoff_application is not None:

        @app.get(
            "/api/v1/handoffs",
            response_model=list[HandoffResponse],
            tags=["Handoff"],
            summary="List open handoff cases",
            responses=error_responses,
        )
        async def list_handoffs(
            principal: PrincipalDependency,
            limit: Annotated[int, Query(ge=1, le=100)] = 50,
        ) -> list[HandoffResponse]:
            handoffs = await handoff_application.list_open(principal, limit=limit)
            return [_handoff_response(handoff) for handoff in handoffs]

        @app.post(
            "/api/v1/handoffs/{handoff_id}/actions",
            response_model=HandoffResponse,
            tags=["Handoff"],
            summary="Apply an authorized handoff lifecycle action",
            responses=error_responses,
        )
        async def transition_handoff(
            handoff_id: UUID,
            request: HandoffActionRequest,
            principal: PrincipalDependency,
        ) -> HandoffResponse:
            handoff = await handoff_application.transition(
                principal, HandoffId(handoff_id), request.action
            )
            return _handoff_response(handoff)

    knowledge_application = services.knowledge
    if knowledge_application is not None:

        @app.post(
            "/api/v1/knowledge/markdown",
            response_model=KnowledgeDocumentResponse,
            status_code=201,
            tags=["Knowledge"],
            summary="Ingest a bounded Markdown knowledge source",
            responses=error_responses,
        )
        async def ingest_markdown(
            request: MarkdownKnowledgeCreate,
            principal: PrincipalDependency,
        ) -> KnowledgeDocumentResponse:
            document = await knowledge_application.ingest_markdown(
                principal,
                title=request.title,
                markdown=request.markdown,
                locale=request.locale,
            )
            return _knowledge_document_response(document)

        @app.post(
            "/api/v1/knowledge/faqs",
            response_model=KnowledgeDocumentResponse,
            status_code=201,
            tags=["Knowledge"],
            summary="Ingest one curated FAQ as an immutable source",
            responses=error_responses,
        )
        async def ingest_faq(
            request: FAQKnowledgeCreate,
            principal: PrincipalDependency,
        ) -> KnowledgeDocumentResponse:
            document = await knowledge_application.ingest_faq(
                principal,
                question=request.question,
                answer=request.answer,
                aliases=request.aliases,
                priority=request.priority,
                locale=request.locale,
            )
            return _knowledge_document_response(document)

        @app.post(
            "/api/v1/knowledge/documents/{document_id}/publish",
            response_model=KnowledgeDocumentResponse,
            tags=["Knowledge"],
            summary="Publish a ready knowledge document",
            responses=error_responses,
        )
        async def publish_knowledge(
            document_id: UUID,
            principal: PrincipalDependency,
        ) -> KnowledgeDocumentResponse:
            document = await knowledge_application.publish(principal, DocumentId(document_id))
            return _knowledge_document_response(document)

        @app.post(
            "/api/v1/knowledge/documents/{document_id}/archive",
            response_model=KnowledgeDocumentResponse,
            tags=["Knowledge"],
            summary="Archive a published or ready knowledge document",
            responses=error_responses,
        )
        async def archive_knowledge(
            document_id: UUID,
            principal: PrincipalDependency,
        ) -> KnowledgeDocumentResponse:
            document = await knowledge_application.archive(principal, DocumentId(document_id))
            return _knowledge_document_response(document)

        @app.post(
            "/api/v1/knowledge/test-answer",
            response_model=KnowledgeAnswerResponse,
            tags=["Knowledge"],
            summary="Evaluate retrieval and citation-backed evidence",
            responses=error_responses,
        )
        async def test_knowledge_answer(
            request: KnowledgeAnswerRequest,
            principal: PrincipalDependency,
        ) -> KnowledgeAnswerResponse:
            return _knowledge_answer_response(
                await knowledge_application.answer(
                    principal,
                    query=request.query,
                    locale=request.locale,
                )
            )

    privacy_application = services.privacy
    if privacy_application is not None:

        @app.get(
            "/api/v1/privacy/data-classifications",
            response_model=list[DataClassificationResponse],
            tags=["Privacy"],
            summary="List the application data-classification inventory",
            responses=error_responses,
        )
        async def list_data_classifications(
            principal: PrincipalDependency,
        ) -> list[DataClassificationResponse]:
            return [
                DataClassificationResponse(
                    data_class=item.data_class.value,
                    purpose=item.purpose,
                    sensitivity=item.sensitivity,
                    retention_action=item.retention_action.value,
                )
                for item in privacy_application.classifications(principal)
            ]

        @app.get(
            "/api/v1/privacy/retention-policy",
            response_model=RetentionPolicyResponse,
            tags=["Privacy"],
            summary="Read the tenant retention policy",
            responses=error_responses,
        )
        async def get_retention_policy(
            principal: PrincipalDependency,
        ) -> RetentionPolicyResponse:
            return _retention_policy_response(await privacy_application.get_policy(principal))

        @app.put(
            "/api/v1/privacy/retention-policy",
            response_model=RetentionPolicyResponse,
            tags=["Privacy"],
            summary="Replace the tenant retention policy with optimistic concurrency",
            responses=error_responses,
        )
        async def update_retention_policy(
            request: RetentionPolicyUpdate,
            principal: PrincipalDependency,
        ) -> RetentionPolicyResponse:
            policy = RetentionPolicy(
                principal.tenant_id,
                request.expected_version + 1,
                request.operational_metadata_days,
                request.message_content_days,
                request.customer_contact_days,
                request.workflow_records_days,
                request.knowledge_archive_days,
                request.ai_telemetry_days,
            )
            return _retention_policy_response(
                await privacy_application.update_policy(
                    principal, policy, expected_version=request.expected_version
                )
            )

        @app.post(
            "/api/v1/privacy/customers/{customer_id}/anonymize",
            response_model=PrivacyResultResponse,
            tags=["Privacy"],
            summary="Anonymize one tenant customer with explicit confirmation",
            responses=error_responses,
        )
        async def anonymize_customer(
            customer_id: UUID,
            request: CustomerAnonymizationRequest,
            principal: PrincipalDependency,
        ) -> PrivacyResultResponse:
            return _privacy_result_response(
                await privacy_application.anonymize_customer(
                    principal,
                    CustomerId(customer_id),
                    confirmed=request.confirmed,
                    idempotency_key=request.idempotency_key,
                    reason_code=request.reason_code,
                )
            )

        @app.get(
            "/api/v1/privacy/retention-preview",
            response_model=PrivacyResultResponse,
            tags=["Privacy"],
            summary="Preview due retention operations without changing data",
            responses=error_responses,
        )
        async def preview_retention(
            principal: PrincipalDependency,
        ) -> PrivacyResultResponse:
            return _privacy_result_response(await privacy_application.preview_retention(principal))

        @app.post(
            "/api/v1/privacy/retention-executions",
            response_model=PrivacyResultResponse,
            tags=["Privacy"],
            summary="Execute due retention operations with explicit confirmation",
            responses=error_responses,
        )
        async def execute_retention(
            request: PrivacyExecutionRequest,
            principal: PrincipalDependency,
        ) -> PrivacyResultResponse:
            return _privacy_result_response(
                await privacy_application.execute_retention(
                    principal,
                    confirmed=request.confirmed,
                    idempotency_key=request.idempotency_key,
                )
            )

    return app
