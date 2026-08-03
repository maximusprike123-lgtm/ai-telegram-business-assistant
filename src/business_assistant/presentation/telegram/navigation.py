"""Validated Telegram presentation orchestration over Phase 3 application queries."""

from dataclasses import dataclass

from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import CategoryNotFoundError
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.telegram import TelegramIdentity
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import CategoryId, ServiceId

from .models import RenderedMessage
from .renderer import TelegramRenderer


@dataclass(frozen=True, slots=True)
class TelegramNavigationServices:
    profile: GetTenantPublicProfile
    categories: ListServiceCategories
    services: ListServices
    service: GetService
    hours: GetBusinessHours
    status: GetBusinessStatus
    next_opening: GetNextOpening
    renderer: TelegramRenderer


class TelegramNavigation:
    def __init__(self, services: TelegramNavigationServices) -> None:
        self._services = services

    @staticmethod
    def _principal(identity: TelegramIdentity) -> Principal:
        return Principal(
            f"telegram-conversation:{identity.conversation_id}", identity.tenant_id, Role.VIEWER
        )

    async def home(self, identity: TelegramIdentity) -> RenderedMessage:
        profile = await self._services.profile.execute(self._principal(identity), identity.locale)
        return self._services.renderer.home(profile)

    async def catalog(self, identity: TelegramIdentity, page: int = 0) -> RenderedMessage:
        categories = await self._services.categories.execute(
            self._principal(identity), identity.locale
        )
        return self._services.renderer.catalog(categories, page)

    async def category(
        self, identity: TelegramIdentity, category_id: CategoryId, page: int = 0
    ) -> RenderedMessage:
        principal = self._principal(identity)
        categories = await self._services.categories.execute(principal, identity.locale)
        category = next((item for item in categories if item.id == str(category_id)), None)
        if category is None:
            raise CategoryNotFoundError()
        services = await self._services.services.execute(principal, identity.locale, category_id)
        return self._services.renderer.services(category, services, page)

    async def service(self, identity: TelegramIdentity, service_id: ServiceId) -> RenderedMessage:
        service = await self._services.service.execute(
            self._principal(identity), service_id, identity.locale
        )
        return self._services.renderer.service(service)

    async def hours(self, identity: TelegramIdentity) -> RenderedMessage:
        principal = self._principal(identity)
        status = await self._services.status.execute(principal)
        days = await self._services.hours.execute(
            principal, status.local_date, days=7, locale=identity.locale
        )
        next_opening = await self._services.next_opening.execute(principal)
        return self._services.renderer.hours(days, status, next_opening)
