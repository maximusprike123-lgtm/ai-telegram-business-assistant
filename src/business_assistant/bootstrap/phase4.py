"""Phase 4 composition root with no network activity at import time."""

from dataclasses import dataclass
from typing import cast

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.token import TokenValidationError, extract_bot_id
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.application.bookings import BookingApplication
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.ports import Phase3UnitOfWork, Phase3UnitOfWorkFactory
from business_assistant.application.common.security import Principal
from business_assistant.application.handoffs import HandoffApplication
from business_assistant.application.leads import (
    QualificationAdministration,
    QualificationApplication,
)
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import ResolveTelegramIdentity, TelegramBotBinding
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.config import ConfigurationError, RuntimeSettings, load_settings
from business_assistant.domain.shared import TenantId
from business_assistant.infrastructure.observability import configure_logging
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBookingStore,
    SQLAlchemyHandoffStore,
    SQLAlchemyQualificationStore,
    SQLAlchemyTelegramIdentityStore,
    SQLAlchemyTelegramUpdateStore,
    create_engine,
    create_session_factory,
)
from business_assistant.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)
from business_assistant.infrastructure.security import StaticApiKeyAuthenticator
from business_assistant.infrastructure.system import UTCClock
from business_assistant.presentation.http import Phase3ApiServices, create_phase3_app
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
    renderer = TelegramRenderer()
    codec = SignedCallbackCodec(
        callback_key,
        version=settings.telegram.callback_version,
        expiry_seconds=settings.telegram.callback_expiry_seconds,
        clock=clock,
    )
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
    )
    return Phase4Components(
        engine,
        session_factory,
        bot,
        build_dispatcher(runtime),
        binding,
        update_store,
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

        @app.middleware("http")
        async def correlation_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
            from uuid import uuid4

            supplied = request.headers.get("X-Request-ID", "")
            request.state.correlation_id = (
                supplied if supplied.isascii() and 1 <= len(supplied) <= 128 else str(uuid4())
            )
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.correlation_id
            return response

        return app
    if (
        security.internal_api_key is None
        or security.internal_api_tenant_id is None
        or security.internal_api_role is None
    ):
        raise ConfigurationError("INTERNAL_API_KEY", "API security context is incomplete")
    clock = UTCClock()
    principal = Principal(
        "static-internal-operator", security.internal_api_tenant_id, security.internal_api_role
    )
    services = Phase3ApiServices(
        GetTenantPublicProfile(uow_factory, clock),
        ListServiceCategories(uow_factory),
        ListServices(uow_factory),
        GetService(uow_factory),
        GetBusinessHours(uow_factory),
        GetBusinessStatus(uow_factory, clock),
        GetNextOpening(uow_factory, clock),
        StaticApiKeyAuthenticator(security.internal_api_key, principal),
        BookingApplication(SQLAlchemyBookingStore(components.session_factory), clock),
        QualificationAdministration(SQLAlchemyQualificationStore(components.session_factory)),
        HandoffApplication(SQLAlchemyHandoffStore(components.session_factory), clock),
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
        await components.bot.session.close()
        await components.engine.dispose()

    app.router.add_event_handler("startup", register_webhook)
    app.router.add_event_handler("shutdown", close_runtime)
    return app


def create_app_from_environment() -> FastAPI:
    return build_phase4_app(load_settings())
