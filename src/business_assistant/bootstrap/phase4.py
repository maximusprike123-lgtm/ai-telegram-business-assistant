"""Phase 4 composition root with no network activity at import time."""

from dataclasses import dataclass
from hmac import compare_digest
from typing import cast

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.token import TokenValidationError, extract_bot_id
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.administration import TenantAdministration
from business_assistant.application.bookings import BookingApplication
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.common.security import Principal
from business_assistant.application.handoffs import HandoffApplication
from business_assistant.application.knowledge import KnowledgeApplication
from business_assistant.application.leads import (
    QualificationAdministration,
    QualificationApplication,
)
from business_assistant.application.observability import correlation_scope, parse_or_create
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import ResolveTelegramIdentity, TelegramBotBinding
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.bootstrap.ai import build_ai_router
from business_assistant.bootstrap.knowledge import build_knowledge_application
from business_assistant.config import ConfigurationError, RuntimeSettings, load_settings
from business_assistant.domain.shared import TenantId
from business_assistant.infrastructure.observability import (
    DependencyHealthChecker,
    PrometheusMetrics,
    configure_logging,
)
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBookingStore,
    SQLAlchemyHandoffStore,
    SQLAlchemyQualificationStore,
    SQLAlchemyTelegramIdentityStore,
    SQLAlchemyTelegramUpdateStore,
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
from business_assistant.presentation.telegram import (
    AiogramDeliveryGateway,
    SignedCallbackCodec,
    TelegramRenderer,
    TelegramRuntime,
    TelegramWebhookServices,
    build_dispatcher,
    install_telegram_webhook,
)
from business_assistant.presentation.telegram.navigation import (
    TelegramNavigation,
    TelegramNavigationServices,
)


@dataclass(frozen=True, slots=True)
class Phase4Components:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    bot: Bot
    dispatcher: Dispatcher
    binding: TelegramBotBinding
    update_store: SQLAlchemyTelegramUpdateStore
    ai_client: httpx.AsyncClient | None
    knowledge: KnowledgeApplication | None
    metrics: PrometheusMetrics


def _require_telegram(settings: RuntimeSettings) -> tuple[str, int, TenantId, str]:
    telegram = settings.telegram
    callback_key = settings.security.callback_signing_key
    if not telegram.enabled:
        raise ConfigurationError("TELEGRAM_ENABLED", "must be enabled")
    if (
        telegram.bot_token is None
        or telegram.bot_id is None
        or telegram.tenant_id is None
        or callback_key is None
    ):
        raise ConfigurationError("TELEGRAM_BOT_TOKEN", "Telegram security context is incomplete")
    try:
        token_bot_id = extract_bot_id(telegram.bot_token)
    except TokenValidationError as exc:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN", "has an invalid format") from exc
    if token_bot_id != telegram.bot_id:
        raise ConfigurationError("TELEGRAM_BOT_ID", "does not match TELEGRAM_BOT_TOKEN")
    return telegram.bot_token, telegram.bot_id, telegram.tenant_id, callback_key


def build_phase4_components(settings: RuntimeSettings) -> Phase4Components:
    token, bot_id, tenant_id_value, callback_key = _require_telegram(settings)
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
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    binding = TelegramBotBinding(bot_id, tenant_id_value)
    renderer = TelegramRenderer(ai_enabled=settings.ai.enabled)
    codec = SignedCallbackCodec(
        callback_key,
        version=settings.telegram.callback_version,
        expiry_seconds=settings.telegram.callback_expiry_seconds,
        clock=clock,
    )
    ai_client = (
        httpx.AsyncClient(timeout=httpx.Timeout(settings.ai.timeout_seconds))
        if settings.ai.enabled
        else None
    )
    metrics = PrometheusMetrics()
    ai_router = build_ai_router(settings, session_factory, ai_client, metrics)
    knowledge = build_knowledge_application(settings, session_factory, ai_client, metrics)
    navigation = TelegramNavigation(
        TelegramNavigationServices(
            GetTenantPublicProfile(typed_factory, clock),
            ListServiceCategories(typed_factory),
            ListServices(typed_factory),
            GetService(typed_factory),
            GetBusinessHours(typed_factory),
            GetBusinessStatus(typed_factory, clock),
            GetNextOpening(typed_factory, clock),
            renderer,
            BookingApplication(SQLAlchemyBookingStore(session_factory), clock),
            QualificationApplication(
                SQLAlchemyQualificationStore(session_factory),
                clock,
                schema_code="service_request",
            ),
            HandoffApplication(SQLAlchemyHandoffStore(session_factory), clock),
            ai_router,
            knowledge,
            SQLAlchemyTenantAccessPolicy(session_factory),
        )
    )
    identity_store = SQLAlchemyTelegramIdentityStore(session_factory)
    update_store = SQLAlchemyTelegramUpdateStore(session_factory)
    logger = configure_logging(settings.observability.log_level, settings.observability.log_format)
    runtime = TelegramRuntime(
        binding,
        navigation,
        renderer,
        AiogramDeliveryGateway(bot, codec),
        codec,
        ResolveTelegramIdentity(identity_store, clock),
        update_store,
        clock,
        settings.telegram.processing_stale_seconds,
        logger,
        metrics,
        SQLAlchemyTenantAccessPolicy(session_factory),
    )
    return Phase4Components(
        engine,
        session_factory,
        bot,
        build_dispatcher(runtime),
        binding,
        update_store,
        ai_client,
        knowledge,
        metrics,
    )


def _internal_api_app(
    settings: RuntimeSettings, components: Phase4Components, uow_factory: Phase3UnitOfWorkFactory
) -> FastAPI:
    security = settings.security
    if not settings.api.enabled:
        app = FastAPI(
            title="AI Telegram Business Assistant",
            version="1.0.0",
            description="English-only Telegram presentation and deterministic business queries.",
        )

        health = DependencyHealthChecker(
            settings,
            components.session_factory,
            components.metrics,
            timeout_seconds=settings.observability.dependency_timeout_seconds,
        )

        @app.middleware("http")
        async def correlation_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
            with correlation_scope(parse_or_create(request.headers.get("X-Request-ID"))) as value:
                request.state.correlation_id = value
                response = await call_next(request)
            response.headers["X-Request-ID"] = value
            return response

        @app.get("/health/live", include_in_schema=False)
        async def liveness() -> dict[str, str]:
            return {"status": "alive"}

        @app.get("/health/ready", include_in_schema=False)
        async def readiness() -> JSONResponse:
            report = await health.check()
            return JSONResponse(
                status_code=200 if report.ready else 503,
                content={"status": "ready" if report.ready else "not_ready"},
            )

        @app.get("/metrics", include_in_schema=False)
        async def metrics(request: Request) -> Response:
            token = settings.observability.metrics_auth_token
            if not settings.observability.metrics_enabled or token is None:
                return Response(status_code=404)
            if not compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
                return Response(status_code=401)
            return Response(
                components.metrics.render(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

        return app
    if (
        security.internal_api_key is None
        or security.internal_api_tenant_id is None
        or security.internal_api_role is None
    ):
        raise ConfigurationError("INTERNAL_API_KEY", "API security context is incomplete")
    clock = UTCClock()
    health = DependencyHealthChecker(
        settings,
        components.session_factory,
        components.metrics,
        timeout_seconds=settings.observability.dependency_timeout_seconds,
    )
    logger = configure_logging(settings.observability.log_level, settings.observability.log_format)
    principal = Principal(
        "static-internal-operator", security.internal_api_tenant_id, security.internal_api_role
    )
    credential_secrets = PBKDF2CredentialSecrets()
    administration_store = SQLAlchemyTenantAdministrationStore(components.session_factory)
    services = Phase3ApiServices(
        GetTenantPublicProfile(uow_factory, clock),
        ListServiceCategories(uow_factory),
        ListServices(uow_factory),
        GetService(uow_factory),
        GetBusinessHours(uow_factory),
        GetBusinessStatus(uow_factory, clock),
        GetNextOpening(uow_factory, clock),
        DatabaseApiKeyAuthenticator(
            components.session_factory,
            credential_secrets,
            StaticApiKeyAuthenticator(security.internal_api_key, principal),
        ),
        BookingApplication(SQLAlchemyBookingStore(components.session_factory), clock),
        QualificationAdministration(SQLAlchemyQualificationStore(components.session_factory)),
        HandoffApplication(SQLAlchemyHandoffStore(components.session_factory), clock),
        components.knowledge,
        operations=OperationalApiServices(
            components.metrics,
            health,
            logger,
            settings.observability.metrics_enabled,
            settings.observability.metrics_auth_token,
            settings.observability.slow_operation_seconds,
        ),
        administration=TenantAdministration(administration_store, credential_secrets),
        tenant_access=SQLAlchemyTenantAccessPolicy(components.session_factory),
        bootstrap_token=security.admin_bootstrap_token,
        request_timeout_seconds=settings.api.request_timeout_seconds,
        max_request_bytes=settings.limits.upload_max_bytes,
    )
    return create_phase3_app(services)


def build_phase4_app(settings: RuntimeSettings) -> FastAPI:
    if settings.telegram.delivery_mode != "webhook":
        raise ConfigurationError("TELEGRAM_DELIVERY_MODE", "must be webhook for the HTTP app")
    components = build_phase4_components(settings)
    session_factory = components.session_factory

    def uow_factory() -> Phase3UnitOfWork:
        return cast(Phase3UnitOfWork, SQLAlchemyUnitOfWork(session_factory))

    typed_factory: Phase3UnitOfWorkFactory = uow_factory
    app = _internal_api_app(settings, components, typed_factory)
    telegram = settings.telegram
    assert telegram.webhook_secret is not None
    assert telegram.webhook_path_secret is not None
    assert telegram.webhook_base_url is not None
    webhook_secret = telegram.webhook_secret
    webhook_path_secret = telegram.webhook_path_secret
    webhook_base_url = telegram.webhook_base_url
    logger = configure_logging(settings.observability.log_level, settings.observability.log_format)
    install_telegram_webhook(
        app,
        TelegramWebhookServices(
            components.dispatcher,
            components.bot,
            components.binding,
            webhook_secret,
            webhook_path_secret,
            telegram.update_max_bytes,
            logger,
        ),
    )

    async def register_webhook() -> None:
        url = f"{webhook_base_url.rstrip('/')}/api/v1/webhooks/telegram/{webhook_path_secret}"
        await components.bot.set_webhook(
            url,
            secret_token=webhook_secret,
            allowed_updates=components.dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )

    async def close_runtime() -> None:
        if components.ai_client is not None:
            await components.ai_client.aclose()
        await components.bot.session.close()
        await components.engine.dispose()

    app.router.add_event_handler("startup", register_webhook)
    app.router.add_event_handler("shutdown", close_runtime)
    return app


def create_app_from_environment() -> FastAPI:
    return build_phase4_app(load_settings())
