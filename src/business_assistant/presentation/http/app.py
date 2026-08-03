"""Thin authenticated Phase 3 FastAPI presentation adapter."""

from dataclasses import dataclass
from datetime import date, datetime
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
from business_assistant.application.scheduling import (
    BusinessDayDTO,
    BusinessStatusDTO,
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
    NextOpeningDTO,
)
from business_assistant.application.tenants import GetTenantPublicProfile, TenantPublicProfileDTO
from business_assistant.domain.shared import CategoryId, ServiceId
from business_assistant.infrastructure.security import StaticApiKeyAuthenticator

from .schemas import (
    AvailabilitySlotResponse,
    BusinessDayResponse,
    BusinessStatusResponse,
    CategoryResponse,
    ErrorResponse,
    NextOpeningResponse,
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
            if exc.code in {"booking.conflict", "booking.expired"}
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

    return app
