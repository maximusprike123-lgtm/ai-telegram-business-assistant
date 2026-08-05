"""Phase 3 composition root; configuration is loaded only here."""

from typing import cast

import httpx
from fastapi import FastAPI

from business_assistant.application.administration import TenantAdministration
from business_assistant.application.background import BackgroundApplication, RetryPolicy
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.common.security import Principal
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.bootstrap.knowledge import build_knowledge_application
from business_assistant.bootstrap.privacy import build_privacy_application
from business_assistant.config import ConfigurationError, RuntimeSettings, load_settings
from business_assistant.infrastructure.observability import (
    DependencyHealthChecker,
    PrometheusMetrics,
    configure_logging,
)
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBackgroundStore,
    SQLAlchemyTenantAccessPolicy,
    SQLAlchemyTenantAdministrationStore,
    create_engine,
    create_session_factory,
)
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)
from business_assistant.infrastructure.security import (
    DatabaseApiKeyAuthenticator,
    PBKDF2CredentialSecrets,
    StaticApiKeyAuthenticator,
)
from business_assistant.infrastructure.system import UTCClock
from business_assistant.presentation.http import (
    OperationalApiServices,
    Phase3ApiServices,
    create_phase3_app,
)


def build_phase3_app(settings: RuntimeSettings) -> FastAPI:
    if not settings.api.enabled:
        raise ConfigurationError("INTERNAL_API_ENABLED", "must be enabled to build the HTTP API")
    security = settings.security
    if (
        security.internal_api_key is None
        or security.internal_api_tenant_id is None
        or security.internal_api_role is None
    ):
        raise ConfigurationError("INTERNAL_API_KEY", "API security context is incomplete")
    database = settings.database
    engine = create_engine(
        database.url,
        pool_size=database.pool_size,
        max_overflow=database.max_overflow,
        connect_timeout_seconds=database.connect_timeout_seconds,
    )
    session_factory = create_session_factory(engine)

    def uow_factory() -> Phase3UnitOfWork:
        return cast(Phase3UnitOfWork, SQLAlchemyUnitOfWork(session_factory))

    typed_factory: Phase3UnitOfWorkFactory = uow_factory
    clock = UTCClock()
    metrics = PrometheusMetrics()
    health = DependencyHealthChecker(
        settings,
        session_factory,
        metrics,
        timeout_seconds=settings.observability.dependency_timeout_seconds,
    )
    logger = configure_logging(settings.observability.log_level, settings.observability.log_format)
    principal = Principal(
        "static-internal-operator", security.internal_api_tenant_id, security.internal_api_role
    )
    credential_secrets = PBKDF2CredentialSecrets()
    administration_store = SQLAlchemyTenantAdministrationStore(session_factory)
    tenant_access = SQLAlchemyTenantAccessPolicy(session_factory)
    ai_client = (
        httpx.AsyncClient(timeout=httpx.Timeout(settings.ai.timeout_seconds))
        if settings.features.rag_enabled
        else None
    )
    services = Phase3ApiServices(
        profile=GetTenantPublicProfile(typed_factory, clock),
        categories=ListServiceCategories(typed_factory),
        services=ListServices(typed_factory),
        service=GetService(typed_factory),
        hours=GetBusinessHours(typed_factory),
        status=GetBusinessStatus(typed_factory, clock),
        next_opening=GetNextOpening(typed_factory, clock),
        authenticator=DatabaseApiKeyAuthenticator(
            session_factory,
            credential_secrets,
            StaticApiKeyAuthenticator(security.internal_api_key, principal),
        ),
        knowledge=build_knowledge_application(settings, session_factory, ai_client, metrics),
        privacy=build_privacy_application(session_factory),
        background=BackgroundApplication(
            SQLAlchemyBackgroundStore(session_factory),
            None,
            clock,
            RetryPolicy(
                settings.celery.max_attempts,
                settings.celery.retry_base_seconds,
                settings.celery.retry_max_seconds,
            ),
            metrics,
        ),
        operations=OperationalApiServices(
            metrics,
            health,
            logger,
            settings.observability.metrics_enabled,
            settings.observability.metrics_auth_token,
            settings.observability.slow_operation_seconds,
        ),
        administration=TenantAdministration(administration_store, credential_secrets),
        tenant_access=tenant_access,
        bootstrap_token=security.admin_bootstrap_token,
        request_timeout_seconds=settings.api.request_timeout_seconds,
        max_request_bytes=settings.limits.upload_max_bytes,
    )
    app = create_phase3_app(services)

    async def close_runtime() -> None:
        if ai_client is not None:
            await ai_client.aclose()
        await engine.dispose()

    app.router.add_event_handler("shutdown", close_runtime)
    return app


def create_app_from_environment() -> FastAPI:
    return build_phase3_app(load_settings())
