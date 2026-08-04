from dataclasses import replace
from datetime import UTC, datetime

import pytest
from tests.helpers_phase3 import phase3_fixture
from tests.unit.test_configuration import telegram_environment, valid_environment

from business_assistant.application.ai import AdvisoryRoute
from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import CategoryNotFoundError
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import ResolveTelegramIdentity, TelegramIdentity
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.bootstrap import telegram_polling
from business_assistant.bootstrap.phase4 import build_phase4_components
from business_assistant.config import ConfigurationError, load_settings
from business_assistant.domain.shared import (
    CategoryId,
    ConversationId,
    CustomerId,
    Locale,
    ServiceId,
    TenantId,
    ValidationError,
)
from business_assistant.presentation.telegram.navigation import (
    TelegramNavigation,
    TelegramNavigationServices,
)
from business_assistant.presentation.telegram.renderer import TelegramRenderer


class IdentityStore:
    def __init__(self, identity: TelegramIdentity) -> None:
        self.identity = identity
        self.arguments = None

    async def resolve(self, tenant_id, **kwargs):
        self.arguments = (tenant_id, kwargs)
        return self.identity


@pytest.mark.asyncio
async def test_identity_use_case_validates_ids_and_passes_minimal_data() -> None:
    uow, principal, clock, _ = phase3_fixture()
    _ = uow
    identity = TelegramIdentity(
        principal.tenant_id, CustomerId.new(), ConversationId.new(), Locale.EN
    )
    store = IdentityStore(identity)
    use_case = ResolveTelegramIdentity(store, clock)
    resolved = await use_case.execute(
        principal.tenant_id,
        external_user_id=123,
        external_chat_id=123,
        requested_locale="fr",
    )
    assert resolved == identity
    assert store.arguments[1]["external_user_id"] == "123"
    assert store.arguments[1]["requested_locale"] == "fr"
    assert store.arguments[1]["now"] == clock.instant
    with pytest.raises(ValidationError, match="user ID"):
        await use_case.execute(
            principal.tenant_id,
            external_user_id=0,
            external_chat_id=1,
            requested_locale=None,
        )
    with pytest.raises(ValidationError, match="chat ID"):
        await use_case.execute(
            principal.tenant_id,
            external_user_id=1,
            external_chat_id=0,
            requested_locale=None,
        )


@pytest.mark.asyncio
async def test_navigation_calls_existing_validated_queries_and_renders_pages() -> None:
    uow, principal, clock, _ = phase3_fixture()

    def factory():
        return uow

    renderer = TelegramRenderer()
    nav_services = TelegramNavigationServices(
        GetTenantPublicProfile(factory, clock),
        ListServiceCategories(factory),
        ListServices(factory),
        GetService(factory),
        GetBusinessHours(factory),
        GetBusinessStatus(factory, clock),
        GetNextOpening(factory, clock),
        renderer,
    )
    navigation = TelegramNavigation(nav_services)
    identity = TelegramIdentity(
        principal.tenant_id, CustomerId.new(), ConversationId.new(), Locale.EN
    )
    assert "Demo Shop" in (await navigation.home(identity)).text
    catalog = await navigation.catalog(identity)
    category_id = CategoryId.parse(catalog.button_rows[0][0].entity_id or "")
    services = await navigation.category(identity, category_id)
    service_id = ServiceId.parse(services.button_rows[0][0].entity_id or "")
    detail = await navigation.service(identity, service_id)
    assert "English description" in detail.text
    hours = await navigation.hours(identity)
    assert "Business hours" in hours.text
    with pytest.raises(CategoryNotFoundError):
        await navigation.category(identity, CategoryId.new())

    class HoursRouter:
        async def route(self, identity, text, *, correlation_id):
            return AdvisoryRoute.HOURS

    routed = TelegramNavigation(
        replace(nav_services, ai_router=HoursRouter())  # type: ignore[arg-type]
    )
    assert (
        "Business hours"
        in (
            await routed.route_free_text(identity, "When are you open?", update_key="fixture:1")
        ).text
    )


def test_telegram_binding_requires_positive_bot_id() -> None:
    from business_assistant.application.telegram import TelegramBotBinding

    with pytest.raises(ValueError, match="positive"):
        TelegramBotBinding(0, TenantId.new())


def test_fixed_clock_fixture_is_aware() -> None:
    assert datetime(2026, 8, 3, tzinfo=UTC).utcoffset() is not None


@pytest.mark.asyncio
async def test_phase4_component_construction_has_no_network_side_effect() -> None:
    settings = load_settings(telegram_environment(mode="polling"))
    components = build_phase4_components(settings)
    try:
        assert components.bot.id == 42
        assert components.binding.tenant_id == settings.telegram.tenant_id
        assert components.dispatcher.resolve_used_update_types() == ["callback_query", "message"]
    finally:
        await components.bot.session.close()
        await components.engine.dispose()


def test_phase4_component_construction_rejects_disabled_invalid_or_mismatched_bot() -> None:
    disabled = load_settings(valid_environment())
    with pytest.raises(ConfigurationError, match="TELEGRAM_ENABLED"):
        build_phase4_components(disabled)

    values = telegram_environment(mode="polling")
    values["TELEGRAM_BOT_TOKEN"] = "invalid"
    with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        build_phase4_components(load_settings(values))

    values = telegram_environment(mode="polling")
    values["TELEGRAM_BOT_ID"] = "43"
    with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_ID"):
        build_phase4_components(load_settings(values))


@pytest.mark.asyncio
async def test_polling_command_refuses_nonlocal_environment_and_webhook_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polling = load_settings(telegram_environment(mode="polling"))
    staging = replace(
        polling,
        application=replace(polling.application, environment="staging"),
    )
    monkeypatch.setattr(telegram_polling, "load_settings", lambda: staging)
    with pytest.raises(ConfigurationError, match="APP_ENV"):
        await telegram_polling.run()

    webhook = load_settings(telegram_environment(mode="webhook"))
    monkeypatch.setattr(telegram_polling, "load_settings", lambda: webhook)
    with pytest.raises(ConfigurationError, match="TELEGRAM_DELIVERY_MODE"):
        await telegram_polling.run()
